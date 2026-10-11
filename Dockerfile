FROM python:3.12-slim

# ffmpeg (avec libmp3lame) + libsndfile pour soundfile
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# yt-dlp a besoin d'un moteur JavaScript (Deno) pour YouTube
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV DATA_DIR=/data \
    HF_HOME=/data/models \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 3000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--proxy-headers", "--forwarded-allow-ips", "*"]
