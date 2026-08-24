#!/usr/bin/env bash
# Recreate AML workspace default storage account if it was deleted.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-visiondostorageae4e2fcd3}"
WORKSPACE="${AZURE_ML_WORKSPACE:-visiondock-ml}"
LOCATION="${LOCATION:-westeurope}"
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"

STORAGE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/${STORAGE_ACCOUNT}"

if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
  echo "Storage account $STORAGE_ACCOUNT already exists."
else
  echo "==> Creating $STORAGE_ACCOUNT (required by AML workspace $WORKSPACE)"
  az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false \
    --min-tls-version TLS1_2 \
    --output none
fi

WS_PRINCIPAL=$(az ml workspace show -g "$RESOURCE_GROUP" -n "$WORKSPACE" --query identity.principalId -o tsv)
echo "==> Grant Storage Blob Data Contributor to workspace MI"
az role assignment create \
  --assignee-object-id "$WS_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID" \
  --output none 2>/dev/null || true

CONN=$(az storage account show-connection-string -n "$STORAGE_ACCOUNT" -g "$RESOURCE_GROUP" -query connectionString -o tsv)
WS_ID=$(az ml workspace show -g "$RESOURCE_GROUP" -n "$WORKSPACE" --query "workspace_id" -o tsv 2>/dev/null || true)
for c in azureml-blobstore azureml azureml-blobstore-v2; do
  az storage container create --name "$c" --connection-string "$CONN" -o none 2>/dev/null || true
done
if [[ -n "$WS_ID" ]]; then
  az storage container create --name "azureml-blobstore-${WS_ID}" --connection-string "$CONN" -o none 2>/dev/null || true
  az storage share create --name "azureml-filestore-${WS_ID}" --connection-string "$CONN" -o none 2>/dev/null || true
fi

echo "==> Sync AML workspace storage keys"
az ml workspace sync-keys -n "$WORKSPACE" -g "$RESOURCE_GROUP" -o none 2>/dev/null || echo "WARN: sync-keys failed — run manually after fixing containers"

echo "Done. Retry Start Training in VisionDock."
