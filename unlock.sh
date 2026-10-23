#!/bin/sh
# === IKONA-ONI ===
# unlock.sh - one-shot launcher (Linux / macOS / WSL / git-bash)
#
#   ./unlock.sh                  install SOUL.md + patch + config + restart
#   ./unlock.sh --dry-run        lihat rencana, tidak menulis apa pun
#   ./unlock.sh --status         status per file
#   ./unlock.sh --restore        rollback
#   ./unlock.sh --skip-soul ...  jangan sentuh SOUL.md
#
# Semua argumen lain diteruskan apa adanya ke hermes_unlock.py.
# Override interpreter: PYTHON=/path/to/python ./unlock.sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) command -v cygpath >/dev/null 2>&1 && HERE=$(cygpath -m "$HERE") ;;
esac

SOUL="--soul"
if [ "${SKIP_SOUL:-0}" = "1" ]; then
  SOUL=""
elif [ "${1:-}" = "--skip-soul" ]; then
  SOUL=""
  shift
fi

# --- interpreter: $PYTHON > hermes venv > python3 > python -----------------
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  GUESS="${HERMES_HOME:-$HOME/.hermes}"
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

echo "[*] interpreter: $PY"
exec "$PY" "$HERE/hermes_unlock.py" $SOUL "$@"
