#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
API_NAME="${API_NAME:-visiondock-api}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/api"
FRONTEND_DIR="$ROOT/artifacts/visiondock"

echo "==> Build frontend"
cd "$FRONTEND_DIR"
if command -v pnpm &>/dev/null; then
  pnpm install --frozen-lockfile 2>/dev/null || pnpm install
  VITE_API_URL="" pnpm exec vite build --config vite.local.config.ts
else
  npm install
  VITE_API_URL="" npx vite build --config vite.local.config.ts
fi

echo "==> Copy UI into api/static"
rm -rf "$API_DIR/static"
cp -R dist/public "$API_DIR/static"

echo "==> Package backend + static"
cd "$API_DIR"
chmod +x startup.sh
zip -qr "$ROOT/backend.zip" . \
  -x ".venv/*" "__pycache__/*" "*.pyc" ".env" ".git/*"

if [[ "${SKIP_AZURE_ML_CONFIG:-}" != "1" ]] && command -v az &>/dev/null; then
  echo "==> Configure Azure ML access (Managed Identity + app settings)"
  if az extension show --name ml &>/dev/null; then
    bash "$(dirname "$0")/configure-azure-ml-access.sh" || echo "WARN: Azure ML configure step failed — set SKIP_AZURE_ML_CONFIG=1 to skip"
  else
    echo "WARN: az ml extension not installed — run: az extension add -n ml"
    echo "      Then: ./scripts/configure-azure-ml-access.sh"
  fi
fi

echo "==> Configure Azure Web App"
# Inline gunicorn — Oryx compressed deploy extracts to /tmp; avoid /home/site/wwwroot/startup.sh
az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --startup-file "gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 600 --access-logfile - --error-logfile - --log-level info" \
  --output none

az webapp log config \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --application-logging filesystem \
  --detailed-error-messages true \
  --web-server-logging filesystem \
  --output none

echo "==> Deploy ZIP"
az webapp deployment source config-zip \
  --resource-group "$RESOURCE_GROUP" \
  --name "$API_NAME" \
  --src "$ROOT/backend.zip" \
  --timeout 900

az webapp restart --resource-group "$RESOURCE_GROUP" --name "$API_NAME" --output none

echo "==> Done: https://${API_NAME}.azurewebsites.net/"
