#!/bin/bash

cd "$(dirname "$0")/.."

docker run -v $(pwd ..):/app/configfiles \
  --env JUSSI_UPSTREAM_CONFIG_FILE=/app/configfiles/DEV_config.json \
  -itp 9000:8080 "$USER/jussi:$(git rev-parse --abbrev-ref HEAD)"
