#!/usr/bin/env bash
set -euo pipefail

mkdir -p /data/logs /data/runner
exec supervisord -c /app/supervisord.conf
