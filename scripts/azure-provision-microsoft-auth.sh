#!/usr/bin/env bash
# Create Azure Entra app registration for VisionDock Microsoft sign-in (no Google Cloud needed).
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
WEBAPP_NAME="${WEBAPP_NAME:-visiondock-api}"
APP_NAME="${APP_NAME:-VisionDock}"
PROD_REDIRECT="${PROD_REDIRECT:-https://visiondock-api.azurewebsites.net/api/auth/microsoft/callback}"
LOCAL_REDIRECT="${LOCAL_REDIRECT:-http://localhost:8000/api/auth/microsoft/callback}"

TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "==> Tenant: $TENANT_ID"

EXISTING_APP_ID="$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || true)"
if [[ -n "$EXISTING_APP_ID" && "$EXISTING_APP_ID" != "None" ]]; then
  APP_ID="$EXISTING_APP_ID"
  OBJECT_ID="$(az ad app show --id "$APP_ID" --query id -o tsv)"
  echo "==> Reusing app registration: $APP_ID"
  az ad app update --id "$OBJECT_ID" \
    --web-redirect-uris "$PROD_REDIRECT" "$LOCAL_REDIRECT" \
    --enable-id-token-issuance true \
    --enable-access-token-issuance true \
    --output none
else
  echo "==> Creating app registration: $APP_NAME"
  APP_ID="$(az ad app create \
    --display-name "$APP_NAME" \
    --sign-in-audience AzureADandPersonalMicrosoftAccount \
    --web-redirect-uris "$PROD_REDIRECT" "$LOCAL_REDIRECT" \
    --enable-id-token-issuance true \
    --enable-access-token-issuance true \
    --query appId -o tsv)"
  OBJECT_ID="$(az ad app show --id "$APP_ID" --query id -o tsv)"
fi

GRAPH_APP_ID="00000003-0000-0000-c000-000000000000"
USER_READ="e1fe6dd8-ba31-4d61-89e7-88639da4683d"
az ad app permission add --id "$OBJECT_ID" --api "$GRAPH_APP_ID" --api-permissions "${USER_READ}=Scope" --output none 2>/dev/null || true
az ad app permission admin-consent --id "$APP_ID" --output none 2>/dev/null || true

echo "==> Creating client secret"
CLIENT_SECRET="$(az ad app credential reset --id "$APP_ID" --display-name visiondock-oauth --years 2 --query password -o tsv)"

echo "==> App Service settings"
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    MICROSOFT_CLIENT_ID="$APP_ID" \
    MICROSOFT_CLIENT_SECRET="$CLIENT_SECRET" \
    AZURE_TENANT_ID="common" \
    MICROSOFT_REDIRECT_URI="$PROD_REDIRECT" \
    FRONTEND_URL="https://visiondock-api.azurewebsites.net" \
  --output none

az webapp restart --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --output none

echo ""
echo "Done."
echo "  App (client) ID: $APP_ID"
echo "  Redirect URI:    $PROD_REDIRECT"
echo "  Tenant:            common (work + personal Microsoft accounts)"
echo ""
echo "Verify: curl https://visiondock-api.azurewebsites.net/api/auth/config"
