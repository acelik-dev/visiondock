#!/usr/bin/env bash
set -euo pipefail

# VisionDock AI — Azure One-Click Deploy Script
# Kullanım: ./scripts/azure-deploy.sh

RESOURCE_GROUP="visiondock-rg"
LOCATION="westeurope"
API_NAME="visiondock-api"
WEB_NAME="visiondock-web"
OPENAI_NAME="visiondock-openai"
PLAN_NAME="visiondock-plan"
KV_NAME="visiondock-kv"

# Renkli output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}VisionDock AI — Azure Deployment${NC}"
echo "=================================="

# 0. Pre-checks
if ! command -v az &> /dev/null; then
    echo -e "${RED}HATA: Azure CLI yüklü değil.${NC} https://aka.ms/installazurecli"
    exit 1
fi

if ! az account show &> /dev/null; then
    echo -e "${RED}HATA: Azure CLI'ya giriş yapılmamış.${NC} 'az login' çalıştırın."
    exit 1
fi

# 1. Resource Group
echo -e "\n${YELLOW}[1/6] Resource Group oluşturuluyor...${NC}"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# 2. Azure OpenAI
echo -e "\n${YELLOW}[2/6] Azure OpenAI Service oluşturuluyor...${NC}"
az cognitiveservices account create \
    --name "$OPENAI_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --kind OpenAI \
    --sku S0 \
    --yes \
    --output none

az cognitiveservices account deployment create \
    --name "$OPENAI_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --deployment-name "gpt-4.1-mini" \
    --model-name "gpt-4.1-mini" \
    --model-version "2025-04-14" \
    --model-format OpenAI \
    --sku-capacity 1 \
    --sku-name "Standard" \
    --output none

# API bilgilerini al
OPENAI_KEY=$(az cognitiveservices account keys list --name "$OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query key1 -o tsv)
OPENAI_ENDPOINT=$(az cognitiveservices account show --name "$OPENAI_NAME" --resource-group "$RESOURCE_GROUP" --query properties.endpoint -o tsv)

echo -e "${GREEN}✓ OpenAI Endpoint:${NC} $OPENAI_ENDPOINT"

# 3. App Service Plan + Web App (Backend)
echo -e "\n${YELLOW}[3/6] Backend (FastAPI) deploy ediliyor...${NC}"

az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku B1 \
    --is-linux \
    --output none

az webapp create \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$PLAN_NAME" \
    --runtime "PYTHON:3.11" \
    --startup-file "startup.txt" \
    --output none

# Environment variables
az webapp config appsettings set \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
        VLM_API_KEY="$OPENAI_KEY" \
        VLM_ENDPOINT="${OPENAI_ENDPOINT%/}/openai/v1" \
        VLM_MODEL="gpt-4.1-mini" \
        PYTHONPATH="/home/site/wwwroot" \
        SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
        WEBSITES_PORT="8000" \
        WEBSITES_CONTAINER_START_TIME_LIMIT="600" \
    --output none

az webapp config set \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --startup-file "bash startup.sh" \
    --output none

az webapp log config \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --application-logging filesystem \
    --detailed-error-messages true \
    --failed-request-tracing true \
    --web-server-logging filesystem \
    --output none

# CORS
az webapp cors add \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --allowed-origins "*" \
    --output none

# Backend ZIP deploy
cd "$(dirname "$0")/../api"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt

chmod +x startup.sh
zip -q -r ../backend.zip . -x ".venv/*" "__pycache__/*" "*.pyc" ".env"

az webapp deploy \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --src-path ../backend.zip \
    --type zip \
    --output none

echo -e "${GREEN}✓ Backend:${NC} https://$API_NAME.azurewebsites.net"

# 4. Static Web App (Frontend)
echo -e "\n${YELLOW}[4/6] Frontend (React) deploy ediliyor...${NC}"

cd "$(dirname "$0")/../artifacts/visiondock"

# Build
VITE_API_URL="https://$API_NAME.azurewebsites.net" npx vite build --config vite.config.ts

# staticwebapp.config.json kopyala
cat > dist/public/staticwebapp.config.json << 'JSONEOF'
{
  "navigationFallback": {
    "rewrite": "/index.html"
  }
}
JSONEOF

az staticwebapp create \
    --name "$WEB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --source ./dist/public \
    --no-wait \
    --output none

echo -e "${GREEN}✓ Frontend:${NC} https://$WEB_NAME.azurestaticapps.net"

# 5. Key Vault (opsiyonel ama önerilir)
echo -e "\n${YELLOW}[5/6] Key Vault oluşturuluyor (secrets yönetimi)...${NC}"
az keyvault create \
    --name "$KV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none

echo -e "${GREEN}✓ Key Vault:${NC} https://$KV_NAME.vault.azure.net"

# 6. Sonuç
echo -e "\n${GREEN}=================================="
echo "DEPLOYMENT TAMAMLANDI"
echo "==================================${NC}"
echo ""
echo "Backend API:     https://$API_NAME.azurewebsites.net"
echo "Frontend Web:    https://$WEB_NAME.azurestaticapps.net"
echo "OpenAI Endpoint: $OPENAI_ENDPOINT"
echo ""
echo "API test: curl https://$API_NAME.azurewebsites.net/"
echo ""
echo -e "${YELLOW}Not: Static Web App'in tam olarak ayağa kalkması 2-3 dakika sürebilir.${NC}"
