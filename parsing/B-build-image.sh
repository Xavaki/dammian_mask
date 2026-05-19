#!/usr/bin/env bash

set -a
source .env
set +a

docker buildx build \
  -t $FULL_IMAGE_NAME \
  .
