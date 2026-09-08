#!/bin/sh
set -e

mkdir -p /app/pdf /app/browser_profile

# Docker creates a directory if a mounted file doesn't exist on the host.
# Replace any such directory with the expected file.
if [ -d /app/output.json ]; then
  rm -rf /app/output.json
fi
[ -f /app/output.json ] || echo '[]' > /app/output.json

exec python server.py