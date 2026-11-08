FROM python:3.12-slim
ENV HUB_DATA=/data/services.json HUB_PORT=29880 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "httpx>=0.27" "docker>=7"
COPY src ./src
COPY web ./web
EXPOSE 29880
HEALTHCHECK --interval=15s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:29880/healthz')"
CMD ["python", "src/app.py"]
