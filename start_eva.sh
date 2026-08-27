#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -f "./.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "./.env"
  set +a
fi
if [ -x "./venv/bin/python3" ]; then
  exec "./venv/bin/python3" main.py
elif [ -x "./.venv/bin/python3" ]; then
  exec "./.venv/bin/python3" main.py
fi
python3 main.py
