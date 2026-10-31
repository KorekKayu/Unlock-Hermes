#!/bin/sh
# === IKONA-ONI ===
# unlock.sh - cukup ini, tanpa flag:
#     ./unlock.sh              pasang semuanya (SOUL + HACKMODE + patch + config + watchdog)
#     ./unlock.sh --status     cek status patch + HACKMODE
#     ./unlock.sh --restore    balikin source asli
#
# Interpreter: $PYTHON > venv Hermes > python3 > python
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) command -v cygpath >/dev/null 2>&1 && HERE=$(cygpath -m "$HERE") ;;
esac

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  GUESS="${HERMES_HOME:-$HOME/AppData/Local/hermes}"
  [ -d "$GUESS" ] || GUESS="$HOME/.hermes"
  for cand in "$GUESS"/installs/*/environments/*/venv/bin/python \
              "$GUESS"/installs/*/venv/bin/python \
              "$GUESS"/installs/*/environments/*/venv/Scripts/python.exe \
              "$GUESS"/installs/*/venv/Scripts/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "ERROR: python tidak ketemu. Install python3, atau set PYTHON=/path/to/python" >&2
  exit 1
fi

exec "$PY" "$HERE/unlock.py" "$@"
