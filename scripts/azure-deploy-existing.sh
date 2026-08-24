#!/usr/bin/env bash
# VisionDock AI — Deploy to EXISTING Azure OpenAI resource
# Usage: ./scripts/azure-deploy-existing.sh

set -euo pipefail

# === YOUR EXISTING RESOURCES ===
RESOURCE_GROUP="vision-doc"
LOCATION="eastus"
OPENAI_NAME="vision-doc-ai"
API_NAME="visiondock-api"
WEB_NAME="visiondock-web"
PLAN_NAME="visiondock-plan"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}VisionDock AI — Deploy to Existing Azure OpenAI${NC}"
echo "================================================"

# === 0. LOGIN ===
echo -e "\n${YELLOW}[0/7] Checking Azure login...${NC}"
if ! az account show &> /dev/null; then
    echo "Running: az login"
    az login
fi
SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${GREEN}✓ Logged in:${NC} $SUBSCRIPTION"

# === 1. VERIFY EXISTING OPENAI ===
echo -e "\n${YELLOW}[1/7] Verifying existing OpenAI resource...${NC}"
OPENAI_KEY=$(az cognitiveservices account keys list \
    --name "$OPENAI_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query key1 -o tsv)

OPENAI_ENDPOINT=$(az cognitiveservices account show \
    --name "$OPENAI_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.endpoint -o tsv)

echo -e "${GREEN}✓ OpenAI:${NC} $OPENAI_ENDPOINT"

# === 2. APP SERVICE PLAN ===
echo -e "\n${YELLOW}[2/7] Creating App Service Plan...${NC}"
az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --sku B1 \
    --is-linux \
    --output none

echo -e "${GREEN}✓ Plan:${NC} $PLAN_NAME"

# === 3. WEB APP (BACKEND) ===
echo -e "\n${YELLOW}[3/7] Creating Web App for Python backend...${NC}"
if az webapp show --name "$API_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${GREEN}✓ Web App already exists:${NC} $API_NAME"
else
    az webapp create \
        --name "$API_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --plan "$PLAN_NAME" \
        --runtime "PYTHON:3.11" \
        --output none
fi

# startup.sh must be executable; logs go to stdout for `az webapp log tail`
az webapp config set \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --startup-file "bash /home/site/wwwroot/startup.sh" \
    --output none

echo -e "${GREEN}✓ Web App:${NC} https://$API_NAME.azurewebsites.net"

# === 4. ENVIRONMENT VARIABLES ===
echo -e "\n${YELLOW}[4/7] Setting environment variables...${NC}"
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

az webapp log config \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --application-logging filesystem \
    --detailed-error-messages true \
    --failed-request-tracing true \
    --web-server-logging filesystem \
    --output none

echo -e "${GREEN}✓ Env vars set${NC}"

# === 5. CORS ===
echo -e "\n${YELLOW}[5/7] Enabling CORS...${NC}"
az webapp cors add \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --allowed-origins "*" \
    --output none

echo -e "${GREEN}✓ CORS enabled${NC}"

# === 6. DEPLOY BACKEND ZIP ===
echo -e "\n${YELLOW}[6/7] Deploying FastAPI backend...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../api"

# Create virtual env and install deps
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt

chmod +x startup.sh

# Create ZIP (exclude venv, cache, env)
zip -q -r ../backend.zip . -x ".venv/*" "__pycache__/*" "*.pyc" ".env" ".git/*"

# Deploy
cd "$SCRIPT_DIR/.."
az webapp deploy \
    --name "$API_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --src-path backend.zip \
    --type zip \
    --output none

echo -e "${GREEN}✓ Backend deployed${NC}"

# === 7. FRONTEND ===
echo -e "\n${YELLOW}[7/7] Building and deploying frontend...${NC}"
cd "$SCRIPT_DIR/../artifacts/visiondock"

# Install deps if needed
if ! command -v pnpm &> /dev/null; then
    npm install -g pnpm
fi
pnpm install

# Build with production API URL
VITE_API_URL="https://$API_NAME.azurewebsites.net" pnpm run build

# Create SWA config for SPA routing
cat > dist/public/staticwebapp.config.json << 'JSONEOF'
{
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/api/*", "/assets/*"]
  },
  "globalHeaders": {
    "content-security-policy": "default-src 'self'; connect-src 'self' https://*.azurewebsites.net; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;"
  }
}
JSONEOF

# Deploy to Static Web Apps
az staticwebapp create \
    --name "$WEB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --source ./dist/public \
    --output none

echo -e "${GREEN}✓ Frontend deployed${NC}"

# === DONE ===
echo -e "\n${GREEN}================================================"
echo "DEPLOYMENT COMPLETE"
echo "================================================${NC}"
echo ""
echo -e "${GREEN}Backend API:${NC}  https://$API_NAME.azurewebsites.net"
echo -e "${GREEN}Frontend Web:${NC} https://$WEB_NAME.azurestaticapps.net"
echo ""
echo "Test API:"
echo "  curl https://$API_NAME.azurewebsites.net/"
echo ""
echo -e "${YELLOW}Note: Static Web App may take 2-3 minutes to be fully ready.${NC}"
