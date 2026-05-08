#!/usr/bin/env bash

IMAGE_NAME='dammian-mask-interface'

docker buildx build \
  --build-context dammian_core=/home/xavaki/DAMM/dammian_core \
  -t ghcr.io/nennisiwok/$IMAGE_NAME:latest \
  .
