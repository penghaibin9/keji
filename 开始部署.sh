#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Only this package's tools; no apt/curl installation, no firewall or host nginx edits.
exec python3 "$ROOT/delivery/manage.py" "$@"
