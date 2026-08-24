#!/bin/bash
set -e

echo "=== Azure App Service Deploy Script ==="

# Cleanup
cd /Users/ahmetahacelik/Downloads/AI-Model-Builder/api
rm -rf .venv __pycache__ *.pyc

cd /Users/ahmetahacelik/Downloads/AI-Model-Builder

# Create proper ZIP (files in root, not in api/ folder)
echo "Creating deployment ZIP..."
rm -f backend.zip
cd api
zip -q -r ../backend.zip . -x ".venv/*" "__pycache__/*" "*.pyc" ".env" "environments/*"
cd ..

echo "ZIP created: $(ls -lh backend.zip)"

# Configure Azure App Service
echo "Configuring Azure App Service..."
az webapp config set \
    --name visiondock-api \
    --resource-group vision-doc \
    --linux-fx-version "PYTHON|3.11" \
    --startup-file "gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120" \
    --output none

az webapp config appsettings set \
    --name visiondock-api \
    --resource-group vision-doc \
    --settings \
        SCM_DO_BUILD_DURING_DEPLOYMENT=true \
        WEBSITE_RUN_FROM_PACKAGE=0 \
        PYTHON_VERSION=3.11 \
    --output none

# Deploy
echo "Deploying to Azure..."
az webapp deploy \
    --name visiondock-api \
    --resource-group vision-doc \
    --src-path backend.zip \
    --type zip \
    --async false

# Restart
echo "Restarting app..."
az webapp restart --name visiondock-api --resource-group vision-doc

echo "=== Deploy Complete ==="
echo "Waiting 60 seconds for startup..."
sleep 60

echo "Testing endpoint..."
curl -s -o /dev/null -w "%{http_code}" https://visiondock-api.azurewebsites.net/ || echo "Not ready yet"
