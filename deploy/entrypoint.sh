#!/bin/sh
# Container entrypoint for speedrun/server.py. Turns env vars into the argv that
# speedrun.server actually parses -- it has NO env-var support of its own
# (speedrun/server.py:490-503: --host/--port/--allow-origin are argv only).
#
#   PORT           the port to bind. Railway/Render inject this. Default 8848.
#   ALLOW_ORIGINS  SPACE-SEPARATED list of page origins allowed to drive the agent.
#                  Required: without it origin_allowed() 403s every browser that
#                  isn't on localhost (speedrun/server.py:104).
#   PAGE_SOURCE    steel (default) | http   -- http is the no-browser fallback.
#   PICKER         llm (default) | first    -- first needs no Anthropic key.
#   NO_PREFLIGHT   any non-empty value adds --no-preflight.
#   VERBOSE        any non-empty value adds -v (one line per HTTP request).
#   PYTHON         interpreter to use. Default `python`.
set -eu

set -- --host 0.0.0.0 --port "${PORT:-8848}" \
       --page-source "${PAGE_SOURCE:-steel}" \
       --picker "${PICKER:-llm}"

# Deliberately unquoted: ALLOW_ORIGINS is a space-separated list and each entry
# becomes its own --allow-origin flag (the flag is action="append").
for origin in ${ALLOW_ORIGINS:-}; do
    set -- "$@" --allow-origin "$origin"
done

[ -n "${NO_PREFLIGHT:-}" ] && set -- "$@" --no-preflight
[ -n "${VERBOSE:-}" ] && set -- "$@" -v

echo "[entrypoint] exec ${PYTHON:-python} -m speedrun.server $*" >&2
# exec so the server is PID 1 and gets the platform's SIGTERM directly: its
# SIGTERM handler is what releases the Steel session (speedrun/server.py:545).
exec "${PYTHON:-python}" -m speedrun.server "$@"
