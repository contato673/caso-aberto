# Servidor Big Field (MMO do Caso Aberto)

Sem dependências: só Python 3.9+. Teste local: `python3 server.py` (porta 8080, ou `PORT=...`).

## Colocar online (Render, plano gratuito)
1. Crie um repositório no GitHub só com esta pasta (server.py, Dockerfile, render.yaml).
2. Em render.com: New > Blueprint (ou Web Service > Docker) apontando para o repositório.
3. Quando subir, a URL será `https://big-field.onrender.com`; o jogo usa `wss://big-field.onrender.com`.
4. Essa URL vai na constante SERVER_URL de scripts/net.gd.

Obs.: no plano gratuito o servidor dorme após ~15 min sem uso (acorda em ~1 min) e o disco é
temporário, então as contas podem ser apagadas num reinício. Para contas permanentes, use um disco persistente.
