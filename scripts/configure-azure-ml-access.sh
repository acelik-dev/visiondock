#!/usr/bin/env bash
# Wire visiondock-api App Service to Azure ML workspace (Managed Identity + app settings).
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
API_NAME="${API_NAME:-visiondock-api}"
WORKSPACE_NAME="${AZURE_ML_WORKSPACE:-visiondock-ml}"
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
LOCATION="${LOCATION:-westeurope}"

echo "==> Subscription: $SUBSCRIPTION_ID"
echo "==> Enable system-assigned managed identity on $API_NAME"
az webapp identity assign \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --output none

PRINCIPAL_ID=$(az webapp identity show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --query principalId -o tsv)

echo "==> Principal ID: $PRINCIPAL_ID"

WS_ID=$(az ml workspace show \
  --name "$WORKSPACE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

echo "==> Grant Contributor on workspace (jobs + environments; compute must exist in Studio)"
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "$WS_ID" \
  --output none 2>/dev/null || echo "(Contributor role may already exist)"

echo "==> Grant AzureML Data Scientist on workspace $WORKSPACE_NAME"
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "AzureML Data Scientist" \
  --scope "$WS_ID" \
  --output none 2>/dev/null || echo "(role may already exist)"

# Storage used by the web app for datasets
STORAGE_ACCOUNT=$(az webapp config appsettings list \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --query "[?name=='AZURE_STORAGE_CONNECTION_STRING'].value | [0]" -o tsv 2>/dev/null || true)

if [[ -z "$STORAGE_ACCOUNT" || "$STORAGE_ACCOUNT" == "null" ]]; then
  echo "==> No storage connection on web app — run scripts/azure-provision-minimal.sh first"
else
  # Extract account name from connection string
  ACCOUNT_NAME=$(echo "$STORAGE_ACCOUNT" | sed -n 's/.*AccountName=\([^;]*\).*/\1/p')
  if [[ -n "$ACCOUNT_NAME" ]]; then
  STORAGE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/${ACCOUNT_NAME}"
  echo "==> Grant Storage Blob Data Contributor on $ACCOUNT_NAME"
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" \
    --scope "$STORAGE_ID" \
    --output none 2>/dev/null || echo "(storage role may already exist)"
  fi
fi

echo "==> App settings for Azure ML"
SETTINGS=(
  "AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
  "AZURE_RESOURCE_GROUP=$RESOURCE_GROUP"
  "AZURE_ML_WORKSPACE=$WORKSPACE_NAME"
  "AZURE_ML_COMPUTE=gpu-cluster"
  "AZURE_ML_VM_SIZE=Standard_NC4as_T4_v3"
  "SCM_DO_BUILD_DURING_DEPLOYMENT=true"
)

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --settings "${SETTINGS[@]}" \
  --output none

echo ""
echo "Done. Deploy app: ./scripts/deploy-visiondock-azure.sh"
echo "Verify: curl https://${API_NAME}.azurewebsites.net/api/training/info"
