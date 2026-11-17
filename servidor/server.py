#!/usr/bin/env python3
"""Servidor MMO "Big Field" do Caso Aberto. Sem dependências (só biblioteca padrão do Python 3.9+).
Contas (usuário + senha com hash), mundo único "big_field", posição dos jogadores em tempo real e chat.
Rodar: python3 server.py   (porta em $PORT, padrão 8080)"""
import asyncio, base64, hashlib, hmac, json, os, secrets, struct, time

PORT = int(os.environ.get("PORT", "8080"))
DATA = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_FILE = os.path.join(DATA, "contas.json")
WORLD = "big_field"
MAX_PLAYERS = 60
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

accounts = {}
players = {}  # id -> dict
next_id = 1


def load_accounts():
    global accounts
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except Exception:
        accounts = {}


def save_accounts():
    try:
        tmp = ACCOUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(accounts, f)
        os.replace(tmp, ACCOUNTS_FILE)
    except Exception as e:
        print("erro ao salvar contas:", e)


def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 60000).hex()


def frame(text, opcode=1):
    data = text.encode() if isinstance(text, str) else text
    n = len(data)
    if n < 126:
        head = struct.pack("!BB", 0x80 | opcode, n)
    elif n < 65536:
        head = struct.pack("!BBH", 0x80 | opcode, 126, n)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 127, n)
    return head + data


async def read_frame(reader):
    h = await reader.readexactly(2)
    opcode = h[0] & 0x0F
    masked = h[1] & 0x80
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack("!H", await reader.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", await reader.readexactly(8))[0]
    if n > 65536:
        raise ValueError("quadro grande demais")
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(n)
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


async def send(p, obj):
    try:
        p["w"].write(frame(json.dumps(obj, separators=(",", ":"))))
        await p["w"].drain()
    except Exception:
        pass


async def broadcast(obj, skip=None):
    for pid, p in list(players.items()):
        if pid != skip and p.get("auth"):
            await send(p, obj)


def clean_name(s):
    s = "".join(ch for ch in str(s).strip() if ch.isalnum() or ch in "_-")
    return s[:16]


async def handle_msg(p, msg):
    t = msg.get("t")
    if t == "auth":
        user = clean_name(msg.get("user", ""))
        pw = str(msg.get("pass", ""))
        if len(user) < 3 or len(pw) < 4:
            return await send(p, {"t": "auth_err", "msg": "Usuário (3+) e senha (4+) são obrigatórios."})
        key = user.lower()
        if msg.get("create"):
            if key in accounts:
                return await send(p, {"t": "auth_err", "msg": "Esse nome já existe."})
            salt = secrets.token_hex(8)
            accounts[key] = {"name": user, "salt": salt, "hash": hash_pw(pw, salt), "created": int(time.time())}
            save_accounts()
        acc = accounts.get(key)
        if not acc or not hmac.compare_digest(acc["hash"], hash_pw(pw, acc["salt"])):
            return await send(p, {"t": "auth_err", "msg": "Usuário ou senha incorretos."})
        for q in players.values():
            if q is not p and q.get("auth") and q["user"] == key:
                return await send(p, {"t": "auth_err", "msg": "Essa conta já está conectada."})
        if sum(1 for q in players.values() if q.get("auth")) >= MAX_PLAYERS:
            return await send(p, {"t": "auth_err", "msg": "Servidor cheio."})
        p.update(auth=True, user=key, name=acc["name"], x=0.0, y=0.0, dir=7, anim="idle", v=0, hide=True)
        await send(p, {"t": "auth_ok", "name": acc["name"], "id": p["id"], "world": WORLD})
        await broadcast({"t": "chat", "name": "Servidor", "text": acc["name"] + " entrou no Big Field."}, skip=p["id"])
        return
    if not p.get("auth"):
        return
    if t == "pos":
        try:
            p["x"] = float(msg["x"]); p["y"] = float(msg["y"])
            p["dir"] = int(msg.get("dir", 7)) & 7
            p["anim"] = str(msg.get("anim", "idle"))[:8]
            p["v"] = int(msg.get("v", 0)) & 7
            p["hide"] = bool(msg.get("hide", False))
        except Exception:
            pass
    elif t == "chat":
        text = str(msg.get("text", ""))[:140].strip()
        if text:
            await broadcast({"t": "chat", "name": p["name"], "text": text})


async def snapshot_loop():
    while True:
        await asyncio.sleep(0.1)
        lst = [[q["id"], q["name"], round(q["x"], 2), round(q["y"], 2), q["dir"], q["anim"], q["v"], 1 if q["hide"] else 0]
               for q in players.values() if q.get("auth")]
        if lst:
            msg = {"t": "players", "list": lst}
            for q in list(players.values()):
                if q.get("auth"):
                    await send(q, msg)


async def client(reader, writer):
    global next_id
    p = None
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin1").split("\r\n")
        path = lines[0].split(" ")[1] if len(lines[0].split(" ")) > 1 else "/"
        hd = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                hd[k.strip().lower()] = v.strip()
        if hd.get("upgrade", "").lower() != "websocket":
            body = json.dumps({"servidor": "Big Field", "online": sum(1 for q in players.values() if q.get("auth"))}).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
            return
        accept = base64.b64encode(hashlib.sha1((hd["sec-websocket-key"] + GUID).encode()).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
        await writer.drain()
        p = {"id": next_id, "w": writer}
        next_id += 1
        players[p["id"]] = p
        while True:
            opcode, payload = await read_frame(reader)
            if opcode == 8:
                break
            if opcode == 9:
                writer.write(frame(payload, 10)); await writer.drain(); continue
            if opcode == 1:
                try:
                    await handle_msg(p, json.loads(payload.decode()))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    finally:
        if p is not None:
            players.pop(p["id"], None)
            if p.get("auth"):
                await broadcast({"t": "left", "id": p["id"]})
        try:
            writer.close()
        except Exception:
            pass


async def main():
    load_accounts()
    server = await asyncio.start_server(client, "0.0.0.0", PORT)
    asyncio.create_task(snapshot_loop())
    print("Big Field online na porta", PORT, flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
