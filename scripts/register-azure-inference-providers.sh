#!/usr/bin/env bash
# Register Azure resource providers required for AML managed online endpoints.
set -euo pipefail

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"

PROVIDERS=(
  Microsoft.MachineLearningServices
  Microsoft.ContainerRegistry
  Microsoft.Network
  Microsoft.Compute
  Microsoft.KeyVault
  Microsoft.Storage
  Microsoft.Insights
  Microsoft.OperationalInsights
  Microsoft.Cdn
  Microsoft.PolicyInsights
)

echo "==> Subscription: $SUBSCRIPTION_ID"
echo "==> Registering providers for AML managed online endpoints…"

for ns in "${PROVIDERS[@]}"; do
  state=$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || echo "Unknown")
  if [[ "$state" == "Registered" ]]; then
    echo "  ✓ $ns (already registered)"
    continue
  fi
  echo "  → $ns ($state) — registering…"
  az provider register --namespace "$ns" --subscription "$SUBSCRIPTION_ID" --wait --output none
  echo "  ✓ $ns"
done

echo "==> Done. Retry inference deploy from the VisionDock UI."
