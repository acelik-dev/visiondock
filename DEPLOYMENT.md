# Azure Deployment Guide — VisionDock AI

Bu rehber, VisionDock AI projesini Azure üzerinde production ortamına taşımak için adım adım talimatları içerir.

---

## Mimari Özeti

| Bileşen | Teknoloji | Azure Servisi |
|---------|-----------|---------------|
| **Frontend** | React 18 + Vite + Tailwind | Azure Static Web Apps |
| **Backend** | Python FastAPI + Uvicorn | Azure App Service (Linux) |
| **AI Model** | Azure OpenAI GPT-4.1-mini | Azure OpenAI Service |
| **Secrets** | — | Azure Key Vault |

---

## Ön Koşullar

1. Azure CLI yüklü ve giriş yapılmış: `az login`
2. Node.js + pnpm yüklü
3. Python 3.11+ yüklü

---

## 1. Azure OpenAI Kurulumu

```bash
# Resource Group oluştur
az group create --name visiondock-rg --location westeurope

# Azure OpenAI Service oluştur
az cognitiveservices account create \
  --name visiondock-openai \
  --resource-group visiondock-rg \
  --location westeurope \
  --kind OpenAI \
  --sku S0 \
  --yes

# GPT-4.1-mini model deployment'ı oluştur
az cognitiveservices account deployment create \
  --name visiondock-openai \
  --resource-group visiondock-rg \
  --deployment-name gpt-4.1-mini \
  --model-name gpt-4.1-mini \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-capacity 1 \
  --sku-name "Standard"

# API Key ve Endpoint al
az cognitiveservices account keys list --name visiondock-openai --resource-group visiondock-rg
az cognitiveservices account show --name visiondock-openai --resource-group visiondock-rg --query properties.endpoint
```

**Not:** Aldığınız `endpoint` ve `key` değerlerini bir yere not edin. Sonraki adımlarda kullanacağız.

---

## 2. Backend Deploy — Azure App Service

### 2.1 App Service Plan oluştur

```bash
az appservice plan create \
  --name visiondock-plan \
  --resource-group visiondock-rg \
  --sku B1 \
  --is-linux
```

### 2.2 Web App oluştur

```bash
az webapp create \
  --name visiondock-api \
  --resource-group visiondock-rg \
  --plan visiondock-plan \
  --runtime "PYTHON:3.11" \
  --startup-file "startup.txt"
```

### 2.3 Environment Variables ayarla

```bash
az webapp config appsettings set \
  --name visiondock-api \
  --resource-group visiondock-rg \
  --settings \
    VLM_API_KEY="<azure-openai-key>" \
    VLM_ENDPOINT="<azure-openai-endpoint>/openai/v1" \
    VLM_MODEL="gpt-4.1-mini" \
    PYTHONPATH="/home/site/wwwroot"
```

### 2.4 ZIP Deploy (en kolay yöntem)

```bash
cd /Users/ahmetahacelik/Downloads/AI-Model-Builder/api

# Sanal ortam oluştur ve bağımlılıkları yükle
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ZIP oluştur
zip -r ../backend.zip . -x ".venv/*" "__pycache__/*" "*.pyc" ".env"

# Deploy et
az webapp deploy \
  --name visiondock-api \
  --resource-group visiondock-rg \
  --src-path ../backend.zip
```

### 2.5 CORS ayarla (Frontend'den erişim için)

```bash
az webapp cors add \
  --name visiondock-api \
  --resource-group visiondock-rg \
  --allowed-origins "*"
```

### 2.6 Doğrula

```bash
curl https://visiondock-api.azurewebsites.net/
# {"status":"VisionDock AI API is running"} görmelisiniz
```

---

## 3. Frontend Deploy — Azure Static Web Apps

### 3.1 Yapılandırma dosyalarını hazırla

`artifacts/visiondock/staticwebapp.config.json` oluştur:

```json
{
  "routes": [
    {
      "route": "/",
      "serve": "/index.html",
      "statusCode": 200
    },
    {
      "route": "/{*}",
      "serve": "/index.html",
      "statusCode": 200
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html"
  }
}
```

### 3.2 Build scriptini ayarla

`artifacts/visiondock/package.json` içinde `build` script şu şekilde olmalı:

```json
"build": "vite build --config vite.config.ts"
```

### 3.3 Static Web App oluştur

```bash
cd /Users/ahmetahacelik/Downloads/AI-Model-Builder/artifacts/visiondock

# Build al (API URL'ini environment variable olarak ver)
VITE_API_URL="https://visiondock-api.azurewebsites.net" pnpm run build

# staticwebapp.config.json'ı dist/public içine kopyala
cp staticwebapp.config.json dist/public/

# Static Web Apps oluştur
az staticwebapp create \
  --name visiondock-web \
  --resource-group visiondock-rg \
  --location westeurope \
  --source ./dist/public \
  --no-wait
```

**Not:** Azure Portal'dan da deploy edebilirsiniz: Static Web Apps > Create > Build Presets: Custom

### 3.4 Doğrula

Browser'da aç: `https://visiondock-web.azurestaticapps.net`

---

## 4. Önemli: Production API URL Ayarı

Frontend'in backend'e doğru adresle istek atması için, `artifacts/visiondock/src/pages/projects.tsx` içindeki API URL'ini production'a göre ayarlayın:

```typescript
// Line ~14 (mevcut sabit yerine)
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

Ve `artifacts/visiondock/vite.config.ts` içinde `define` ekleyin:

```typescript
export default defineConfig({
  // ... mevcut ayarlar
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL || 'http://localhost:8000'),
  },
});
```

---

## 5. Güvenlik: Key Vault ile Secrets Yönetimi (Önerilen)

```bash
# Key Vault oluştur
az keyvault create --name visiondock-kv --resource-group visiondock-rg --location westeurope

# Secret ekle
az keyvault secret set --vault-name visiondock-kv --name VlmApiKey --value "<azure-openai-key>"

# App Service'e Key Vault erişimi ver
az webapp identity assign --name visiondock-api --resource-group visiondock-rg

# (Key Vault > Access policies'dan App Service'e Secret Get izni verin)
```

---

## 5a. Minimum-cost Azure kaynakları (Cosmos DB yok)

Sadece **Blob Storage** eklenir (~\$0.02/GB/ay). Proje verisi JSON + dosyalar blob’da tutulur.

```bash
chmod +x scripts/azure-provision-minimal.sh
./scripts/azure-provision-minimal.sh
```

Portal’da görmeniz gerekenler (`vision-doc` RG):

| Kaynak | Tip |
|--------|-----|
| vision-doc | Resource group |
| visiondock-api | App Service |
| vision-doc-ai | Azure OpenAI |
| **visiondocstore661f** | Storage account (Blob, West Europe) |

**Portal notu:** “Recent resources” yalnızca son açtığınız kaynakları gösterir. Storage’ı görmek için **Resource groups → vision-doc** açın veya arama kutusuna `visiondocstore661f` yazın.

App Service plan (`visiondock-plan`) listede görünmeyebilir — App Service’e bağlıdır.

**Hızlı deploy** (CLI 15 dk beklemesin):

```bash
az webapp deploy -g vision-doc -n visiondock-api --src-path backend.zip --type zip --async true
# ~3 dk sonra
az webapp restart -g vision-doc -n visiondock-api
```

---

## 5b. Login sayfası (session auth)

Tarayıcı popup yok — uygulama içi `/` login ekranı gösterir.

```bash
az webapp config appsettings set -g vision-doc -n visiondock-api --settings \
  AUTH_ENABLED=true \
  AUTH_USERNAME="admin@hiddenslate.com" \
  AUTH_PASSWORD="<your-password>" \
  AUTH_SESSION_SECRET="<random-64-char-string>"
```

`BASIC_AUTH_*` değişken adları da desteklenir. Kapatmak için `AUTH_ENABLED=false`.

---

## 6. Monitoring ve Logs

**Önemli:** Gunicorn varsayılan olarak dosyaya log yazar; container log stream’de Python hatası görünmez. `api/startup.sh` stdout’a log yazar (`--access-logfile - --error-logfile -`).

```bash
# Log streaming aç (bir kez)
az webapp log config \
  --name visiondock-api \
  --resource-group vision-doc \
  --application-logging filesystem \
  --detailed-error-messages true \
  --web-server-logging filesystem

# Canlı logları izle (gerçek gunicorn/uvicorn çıktısı)
az webapp log tail --name visiondock-api --resource-group vision-doc

# Startup komutunu doğrula
az webapp config show --name visiondock-api --resource-group vision-doc \
  --query appCommandLine -o tsv
# Beklenen: bash startup.sh
```

### Container exit code 3 / timeout

| Neden | Çözüm |
|--------|--------|
| Startup komutu yok veya yanlış (`application:app` aranıyor) | `az webapp config set --startup-file "bash startup.sh"` |
| Port uyumsuzluğu | `WEBSITES_PORT=8000`, gunicorn `--bind 0.0.0.0:${PORT}` |
| B1’de 2 worker OOM | `WEB_CONCURRENCY=1` (startup.sh varsayılanı) |
| `VLM_ENDPOINT` birleşik URL hatası | `https://....azure.com/openai/v1` (`/openai/v1` öncesi `/` olmalı) |
| Kudu 401 | Publish profile veya `az webapp log tail`; SCM için portal → Advanced Tools → Go |

Hızlı onarım (mevcut `vision-doc` RG):

```bash
cd api && chmod +x startup.sh
zip -r ../backend.zip . -x ".venv/*" "__pycache__/*" "*.pyc" ".env"

az webapp config set -g vision-doc -n visiondock-api --startup-file "bash startup.sh"
az webapp config appsettings set -g vision-doc -n visiondock-api --settings \
  WEBSITES_PORT=8000 WEBSITES_CONTAINER_START_TIME_LIMIT=600 WEB_CONCURRENCY=1

az webapp deploy -g vision-doc -n visiondock-api --src-path ../backend.zip --type zip
az webapp restart -g vision-doc -n visiondock-api
az webapp log tail -g vision-doc -n visiondock-api
```

---

## 7. Cleanup (Silme)

```bash
az group delete --name visiondock-rg --yes --no-wait
```

---

## Hızlı Komutlar Özeti

```bash
# Tek seferde her şeyi deploy et
./scripts/azure-deploy.sh
```

Ayrıca `.github/workflows/azure-deploy.yml` workflow'u ile otomatik CI/CD kurulumu yapabilirsiniz.
