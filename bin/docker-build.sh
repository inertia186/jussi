#!/bin/bash

cd "$(dirname "$0")/.."

docker build -t="$USER/jussi:$(git rev-parse --abbrev-ref HEAD)" .
