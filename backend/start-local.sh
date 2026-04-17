#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 start_local_backend.py --host 127.0.0.1 --port 8000
