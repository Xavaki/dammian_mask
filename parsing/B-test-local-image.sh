#!/usr/bin/env bash

set -a
source .env
set +a

envsubst <.env.template >.env

docker run --rm --env-file .env $FULL_IMAGE_NAME
