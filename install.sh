#!/bin/sh
set -eu
SHOPDATE_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${SHOPDATE_PYTHON:-}" ]; then
    exec "$SHOPDATE_PYTHON" "$SHOPDATE_ROOT/installer.py" "$@"
elif [ -x "$SHOPDATE_ROOT/.venv/bin/python" ]; then
    exec "$SHOPDATE_ROOT/.venv/bin/python" "$SHOPDATE_ROOT/installer.py" "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 "$SHOPDATE_ROOT/installer.py" "$@"
else
    echo 'Install Python 3.11+ first, or set SHOPDATE_PYTHON to its absolute path.' >&2
    exit 1
fi
