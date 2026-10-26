# The adventure renderer (Node): dependencies built for this platform, without dev tools.
FROM node:22.20.0-bookworm-slim AS adventure
WORKDIR /srv/adventure
COPY adventure/package.json adventure/package-lock.json adventure/.npmrc ./
COPY adventure/packages/engine/package.json packages/engine/
COPY adventure/packages/renderer/package.json packages/renderer/
COPY adventure/packages/shared/package.json packages/shared/
RUN npm ci --omit=dev
COPY adventure/ ./

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-noto-color-emoji libfribidi0 libharfbuzz0b libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=adventure /usr/local/bin/node /usr/local/bin/node
COPY --from=adventure /srv/adventure /srv/adventure

ENV DATA_DIR=/data PYTHONUNBUFFERED=1 ADVENTURE_DIR=/srv/adventure
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
