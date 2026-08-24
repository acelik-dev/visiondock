#!/usr/bin/env bash
# Reduce GPU queue time by keeping the cluster warm longer between jobs.
# Trade-off: slightly higher cost if nodes stay up while idle.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-vision-doc}"
WORKSPACE="${AZURE_ML_WORKSPACE:-visiondock-ml}"
COMPUTE="${AZURE_ML_COMPUTE:-gpu-cluster}"
# Keep nodes up 15 min after last job (default is 120s → frequent cold starts)
IDLE_SECONDS="${IDLE_SECONDS:-900}"
# Set MIN_NODES=1 to always keep one GPU warm (~continuous cost). Default 0 = scale to zero.
MIN_NODES="${MIN_NODES:-0}"

echo "==> Updating $COMPUTE (idle_time_before_scale_down=${IDLE_SECONDS}s, min_instances=${MIN_NODES})"
az ml compute update \
  --name "$COMPUTE" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE" \
  --idle-time-before-scale-down "$IDLE_SECONDS" \
  --min-instances "$MIN_NODES"

echo "==> Done. Next training should queue less if jobs run within ${IDLE_SECONDS}s of each other."
if [[ "$MIN_NODES" == "0" ]]; then
  echo "    Tip: MIN_NODES=1 ./scripts/tune-gpu-cluster-queue.sh  # instant start, higher cost"
fi
