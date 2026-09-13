# The agent server, containerised for Render. FRONTEND.md §9, README "Deploying the app".
#
# ONLY the Python half is in here. The frontend is served by Vercel; `web/` is
# excluded via .dockerignore so a UI change never rebuilds this image.
#
# This cannot be a serverless function, which is why it needs a host like Render
# at all: `speedrun/server.py` keeps the RaceManager, the EventLog, the Steel
# session and the `go` event in PROCESS MEMORY, and POST /race -> GET /events ->
# POST /race/<id>/go are three separate requests that must share all of it.
# It follows that this service must stay at ONE instance -- see render.yaml.
FROM python:3.11-slim-bookworm

# curl: the steel installer checks for it explicitly and exits if missing.
# ca-certificates: the installer and every api.steel.dev / api.anthropic.com call.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# The Steel CLI, native binary. NOT `npm i -g @steel-dev/cli`, which is now a
# slower shim (CLAUDE.md). The installer writes to $HOME/.steel/bin and wants to
# edit shell rc files; STEEL_CLI_NO_MODIFY_PATH=1 stops that, and we copy the
# binary to /usr/local/bin so it is on PATH regardless of HOME or which user
# ends up running the process. Credentials come from STEEL_API_KEY at runtime --
# verified: `steel doctor` reports `source: "env (STEEL_API_KEY)"` and passes
# with no config file present, which is why no `steel login` is needed here.
RUN STEEL_CLI_NO_MODIFY_PATH=1 curl -fsS https://setup.steel.dev | sh \
 && cp "$HOME/.steel/bin/steel" /usr/local/bin/steel \
 && chmod +x /usr/local/bin/steel \
 && steel --version

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY speedrun/ ./speedrun/
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8848
CMD ["./docker-entrypoint.sh"]
