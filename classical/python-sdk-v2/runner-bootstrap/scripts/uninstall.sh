#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP=${ARC_RESOURCE_GROUP:-rg-mlops-arc-dev-eus2-001}
AKS_NAME=${ARC_AKS_NAME:-aks-mlops-arc-dev-eus2-001}
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [[ ${1:-} == arc ]]; then
  python3 "$ROOT_DIR/scripts/invoke_aks_command.py" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$AKS_NAME" \
    --print-logs \
    --command '
    helm uninstall mlops-private -n arc-runners || true
    kubectl delete secret arc-github-app -n arc-runners --ignore-not-found
    helm uninstall arc -n arc-systems || true
  '
elif [[ ${1:-} == infrastructure ]]; then
  echo "Delete ARC first, then delete resource group $RESOURCE_GROUP manually after reviewing dependencies."
  echo "The shared hub VNet is not deleted. Remove only subnet snet-github-runners after AKS deletion completes."
  exit 2
else
  echo "Usage: $0 arc|infrastructure"
  exit 2
fi
