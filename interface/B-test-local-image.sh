#!/usr/bin/env bash

IMAGE_NAME='dammian-mask-interface'

docker run --rm -p 5000:5000 --env-file backend/.env ghcr.io/nennisiwok/$IMAGE_NAME:latest

