#!/usr/bin/env bash
# Cheapest Azure PostgreSQL Flexible Server for VisionDock auth (Google OAuth users).
# Tier: Burstable B1ms, 32 GB storage, single zone — ~$12–15/month (region-dependent).
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-visiondock-rg}"
LOCATION="${LOCATION:-swedencentral}"
WEBAPP_NAME="${WEBAPP_NAME:-visiondock-api-ataha}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
PG_SERVER="${PG_SERVER:-visiondock-pg-ataha}"
PG_ADMIN_USER="${PG_ADMIN_USER:-visiondockadmin}"
PG_DB="${PG_DB:-visiondock}"
PG_SKU="${PG_SKU:-Standard_B1ms}"
PG_STORAGE_GB="${PG_STORAGE_GB:-32}"
PG_VERSION="${PG_VERSION:-16}"

if [[ -z "${PG_ADMIN_PASSWORD:-}" ]]; then
  # Alphanumeric only so DATABASE_URL needs no percent-encoding.
  PG_ADMIN_PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 28)"
  echo "Generated PG_ADMIN_PASSWORD (save this): $PG_ADMIN_PASSWORD"
fi

echo "==> Subscription: $SUBSCRIPTION_ID"
echo "==> Registering Microsoft.DBforPostgreSQL (first time only)..."
az provider register --namespace Microsoft.DBforPostgreSQL --subscription "$SUBSCRIPTION_ID" --wait --output none 2>/dev/null || true

echo "==> PostgreSQL Flexible Server: $PG_SERVER ($PG_SKU, ${PG_STORAGE_GB}GB, single zone)"
if az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$PG_SERVER" &>/dev/null; then
  echo "Server already exists — updating admin password and continuing"
  az postgres flexible-server update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER" \
    --admin-password "$PG_ADMIN_PASSWORD" \
    --output none
else
  az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER" \
    --location "$LOCATION" \
    --subscription "$SUBSCRIPTION_ID" \
    --admin-user "$PG_ADMIN_USER" \
    --admin-password "$PG_ADMIN_PASSWORD" \
    --sku-name "$PG_SKU" \
    --tier Burstable \
    --storage-size "$PG_STORAGE_GB" \
    --version "$PG_VERSION" \
    --public-access 0.0.0.0 \
    --yes \
    --output none
fi

echo "==> Database: $PG_DB"
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name "$PG_DB" \
  --output none 2>/dev/null || true

echo "==> Allow Azure services (App Service outbound) to reach Postgres"
az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 \
  --output none 2>/dev/null || true

FQDN=$(az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$PG_SERVER" --query fullyQualifiedDomainName -o tsv)
DATABASE_URL="postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${FQDN}:5432/${PG_DB}?sslmode=require"

echo "==> Web App settings ($WEBAPP_NAME)"
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    DATABASE_URL="$DATABASE_URL" \
  --output none

echo ""
echo "Done."
echo "  Server:       $FQDN"
echo "  Database:     $PG_DB"
echo "  Admin user:   $PG_ADMIN_USER"
echo "  SKU:          Burstable $PG_SKU (${PG_STORAGE_GB}GB)"
echo ""
echo "Restart the web app so tables are created:"
echo "  az webapp restart -g $RESOURCE_GROUP -n $WEBAPP_NAME"
echo ""
echo "Local dev DATABASE_URL (add to api/.env):"
echo "  DATABASE_URL=$DATABASE_URL"
