#!/usr/bin/env bash
set -a
source .env
set +a
az containerapp job create \
  --name $CONTAINER_APP_PARSING_JOB_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_PARSING_ENV \
  --trigger-type Event \
  --replica-timeout 1800 \
  --replica-retry-limit 2 \
  --replica-completion-count 1 \
  --parallelism 3 \
  --cpu 1.0 \
  --memory 2Gi \
  --polling-interval 5 \
  --image $FULL_IMAGE_NAME \
  --registry-server $REGISTRY_SERVER \
  --registry-username $REGISTRY_USERNAME \
  --registry-password $REGISTRY_PASSWORD \
  --secrets \
  azure-openai-api-key=$AZURE_OPENAI_API_KEY \
  azure-tenant-client-secret=$AZURE_CLIENT_SECRET \
  azure-queue-conn-string=$STORAGE_ACCOUNT_CONNECTION_STRING \
  --env-vars \
  AZURE_CLIENT_ID=$AZURE_CLIENT_ID \
  AZURE_TENANT_ID=$AZURE_TENANT_ID \
  AZURE_CLIENT_SECRET=secretref:azure-tenant-client-secret \
  AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
  AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION \
  AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT \
  STORAGE_ACCOUNT_RESOURCE_URL=$STORAGE_ACCOUNT_RESOURCE_URL \
  QUEUE_URL=$QUEUE_URL \
  QUEUE_NAME=$QUEUE_NAME \
  --scale-rule-name queue-trigger \
  --scale-rule-type azure-queue \
  --scale-rule-metadata \
  queueName=$QUEUE_NAME \
  queueLength=1 \
  accountName=$ACCOUNT_NAME \
  --scale-rule-auth \
  connection=azure-queue-conn-string
