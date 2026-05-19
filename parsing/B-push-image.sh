#!/usr/bin/env bash
set -a
source .env
set +a

docker push $FULL_IMAGE_NAME
