#!/usr/bin/env bash
# Set Google OAuth credentials on visiondock-api App Service.
# Usage:
#   GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com \
#   GOOGLE_CLIENT_SECRET=yyy \
#   ./scripts/configure-google-oauth.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
WEBAPP_NAME="${WEBAPP_NAME:-visiondock-api}"

if [[ -z "${GOOGLE_CLIENT_ID:-}" || -z "${GOOGLE_CLIENT_SECRET:-}" ]]; then
  echo "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars." >&2
  exit 1
fi

OAUTH_REDIRECT_URI="${OAUTH_REDIRECT_URI:-https://visiondock-api.azurewebsites.net/api/auth/google/callback}"
FRONTEND_URL="${FRONTEND_URL:-https://visiondock-api.azurewebsites.net}"

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
    GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET" \
    OAUTH_REDIRECT_URI="$OAUTH_REDIRECT_URI" \
    FRONTEND_URL="$FRONTEND_URL" \
  --output none

az webapp restart --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --output none
echo "Google OAuth configured. Verify: curl https://visiondock-api.azurewebsites.net/api/auth/config"
