#!/bin/bash

cd "$(dirname "$0")/.."

docker run -itp 9000:8080 "$USER/jussi:$(git rev-parse --abbrev-ref HEAD)"
