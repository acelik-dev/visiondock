# Google OAuth for VisionDock

VisionDock uses a **custom OAuth2 flow in FastAPI** (not App Service Easy Auth) so the existing session-cookie auth and SPA stay unchanged.

## 1. Create Google Cloud OAuth client

1. Open [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. **Create Credentials** → **OAuth client ID** → Application type: **Web application**.
3. Name: `VisionDock` (any name).
4. **Authorized JavaScript origins** (optional for this server-side flow):
   - `https://visiondock-api.azurewebsites.net`
   - `http://localhost:8080`
5. **Authorized redirect URIs** (required):
   - Production: `https://visiondock-api.azurewebsites.net/api/auth/google/callback`
   - Local dev: `http://localhost:8000/api/auth/google/callback`
6. Copy **Client ID** and **Client secret**.

If prompted, configure the OAuth consent screen (External, add your email as test user for development).

## 2. Azure App Service settings

After `./scripts/azure-provision-postgres.sh` (or with SQLite locally):

```bash
RESOURCE_GROUP=vision-doc
WEBAPP_NAME=visiondock-api

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    GOOGLE_CLIENT_ID="YOUR_CLIENT_ID.apps.googleusercontent.com" \
    GOOGLE_CLIENT_SECRET="YOUR_CLIENT_SECRET" \
    OAUTH_REDIRECT_URI="https://visiondock-api.azurewebsites.net/api/auth/google/callback" \
    SESSION_SECRET="$(openssl rand -hex 32)" \
    AUTH_ENABLED=true
```

Legacy email/password sign-in still works if `AUTH_USERNAME` and `AUTH_PASSWORD` remain set.

## 3. Local development

Add to `api/.env`:

```env
DATABASE_URL=sqlite:///./data/visiondock.db
# Or use the Postgres URL from azure-provision-postgres.sh

GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
FRONTEND_URL=http://localhost:8080
SESSION_SECRET=dev-only-change-me

# Optional: keep password login during migration
AUTH_USERNAME=admin@example.com
AUTH_PASSWORD=change-me
```

Run backend on port 8000 and frontend on 8080. Click **Continue with Google** — callback hits the API, then redirects to the Vite dev server.

## Architecture notes

| Component | Choice | Why |
|-----------|--------|-----|
| OAuth | FastAPI + httpx | Reuses session cookies; no Easy Auth / Entra rework |
| Database | Azure Postgres Flexible **Burstable B1ms** | Cheapest managed Postgres; SQLite fallback when `DATABASE_URL` unset |
| Users table | `id, email, name, google_sub, created_at, last_login` | Minimal schema for social login |

Estimated Postgres cost: ~$12–15/month (West Europe, B1ms, 32 GB).
