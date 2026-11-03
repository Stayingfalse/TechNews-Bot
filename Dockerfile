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
# APP=app.render_worker:app runs this image as the render worker (docs/SETUP.md, "Render worker");
# PORT is for hosts that choose the port themselves.
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/health')"
CMD ["sh", "-c", "exec uvicorn \"${APP:-app.main:app}\" --host 0.0.0.0 --port \"${PORT:-8000}\""]
