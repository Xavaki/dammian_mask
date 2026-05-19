#!/usr/bin/env bash
set -a
source .env
set +a

az containerapp job update \
  --name $CONTAINER_APP_PARSING_JOB_NAME \
  --resource-group $RESOURCE_GROUP \
  --image $FULL_IMAGE_NAME
