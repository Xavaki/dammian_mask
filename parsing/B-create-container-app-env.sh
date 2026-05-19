#!/usr/bin/env bash
set -a
source .env
set +a
exit 0
az containerapp env create \
  --name $CONTAINER_APP_PARSING_ENV \
  --resource-group $RESOURCE_GROUP \
  --location spaincentral
