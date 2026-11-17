FROM python:3.12-slim
WORKDIR /app
COPY server.py .
ENV PORT=8080 DATA_DIR=/data
RUN mkdir -p /data
CMD ["python3", "server.py"]
