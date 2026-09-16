#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP=${ARC_RESOURCE_GROUP:-rg-mlops-arc-dev-eus2-001}
AKS_NAME=${ARC_AKS_NAME:-aks-mlops-arc-dev-eus2-001}
GITHUB_REPOSITORY=${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be owner/repository}
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 "$ROOT_DIR/scripts/invoke_aks_command.py" \
  --resource-group "$RESOURCE_GROUP" \
  --name "$AKS_NAME" \
  --print-logs \
  --command '
set -e
kubectl get pods -n arc-systems
kubectl get pods -n arc-runners
kubectl get autoscalingrunnersets -n arc-runners
kubectl run arc-egress-check --rm -i --restart=Never --image=curlimages/curl:8.12.1 -- sh -ec "
  for host in github.com api.github.com ghcr.io management.azure.com login.microsoftonline.com pypi.org; do
    nslookup \$host >/dev/null
    curl --silent --show-error --head --max-time 20 https://\$host >/dev/null
  done
"
'

env -u GH_TOKEN gh api "repos/$GITHUB_REPOSITORY/actions/runners" \
  --jq '{total_count, runners: [.runners[] | {name,status,busy,labels:[.labels[].name]}]}'
