#!/bin/sh
# Render (and every PaaS) injects $PORT at runtime and expects the process to
# bind 0.0.0.0. server.py defaults to 127.0.0.1:8848, which would be reachable
# only from inside the container, so both have to be passed explicitly.
#
# This is a script rather than a CMD string because the argument list is
# conditional: ALLOW_ORIGIN may be unset, and a JSON-array CMD does not expand
# variables at all.
set -eu

PORT="${PORT:-8848}"

set -- --host 0.0.0.0 --port "$PORT"

# The Vercel page's origin. CORS is not a security boundary -- curl ignores it --
# but it is what stops an unrelated site from driving your agent from a
# visitor's browser. Comma-separated for more than one (production + a preview).
if [ -n "${ALLOW_ORIGIN:-}" ]; then
  OLDIFS=$IFS; IFS=,
  for origin in $ALLOW_ORIGIN; do
    [ -n "$origin" ] && set -- "$@" --allow-origin "$origin"
  done
  IFS=$OLDIFS
fi

# Escape hatches, both default off: run without a browser if Steel is down
# (FRONTEND.md §9.3 lever 2), or with the keyless dev picker.
[ "${PAGE_SOURCE:-}" = "http" ] && set -- "$@" --page-source http
[ "${PICKER:-}" = "first" ] && set -- "$@" --picker first

echo "[entrypoint] python -m speedrun.server $*"
exec python -m speedrun.server "$@"
