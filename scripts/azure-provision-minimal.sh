#!/usr/bin/env bash
# Minimum-cost Azure resources for VisionDock (no Cosmos DB).
# Creates: Storage Account (Blob) + app settings on existing Web App.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
LOCATION="${LOCATION:-westeurope}"
WEBAPP_NAME="${WEBAPP_NAME:-visiondock-api}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
# Storage account: 3-24 lowercase letters/numbers, globally unique
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-visiondocstore$(openssl rand -hex 2)}"
CONTAINER="${AZURE_STORAGE_CONTAINER:-visiondock}"

echo "==> Subscription: $SUBSCRIPTION_ID"
echo "==> Registering Microsoft.Storage (first time only)..."
az provider register --namespace Microsoft.Storage --subscription "$SUBSCRIPTION_ID" --wait --output none 2>/dev/null || true

echo "==> Storage account: $STORAGE_ACCOUNT (Standard LRS — lowest cost tier)"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Hot \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --output none

CONN=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

az storage container create \
  --name "$CONTAINER" \
  --connection-string "$CONN" \
  --output none 2>/dev/null || true

echo "==> Web App settings"
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    STORAGE_BACKEND=azure \
    AZURE_STORAGE_CONTAINER="$CONTAINER" \
    AZURE_STORAGE_CONNECTION_STRING="$CONN" \
    MAX_DATASET_ZIP_BYTES=536870912 \
  --output none

echo ""
echo "Done."
echo "  Storage account: $STORAGE_ACCOUNT"
echo "  Container:       $CONTAINER"
echo "  Est. cost:       ~\$0.02/GB/month storage + existing App Service plan"
echo ""
echo "Deploy app: ./scripts/deploy-visiondock-azure.sh"
