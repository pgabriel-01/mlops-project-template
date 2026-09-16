#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$ROOT_DIR/scripts/deployment_config.sh"
DEPLOYMENT_NAME=${DEPLOYMENT_NAME:-mlops-arc-bootstrap}
PARAMETER_OVERRIDES=(
  "location=$LOCATION"
  "hubVnetResourceGroupName=$HUB_RESOURCE_GROUP"
  "hubVnetName=$HUB_VNET"
  "runnerSubnetPrefix=$RUNNER_SUBNET_PREFIX"
  "runnerSubnetName=$RUNNER_SUBNET_NAME"
  "nodeVmSize=$NODE_SKU"
  "systemNodeCount=$SYSTEM_NODE_COUNT"
)

usage() {
  echo "Usage: $0 what-if|apply"
}

[[ $# -eq 1 ]] || { usage; exit 2; }

export LOCATION
export ARC_HUB_RESOURCE_GROUP="$HUB_RESOURCE_GROUP"
export ARC_HUB_VNET="$HUB_VNET"
export ARC_RUNNER_SUBNET_PREFIX="$RUNNER_SUBNET_PREFIX"
export ARC_RUNNER_SUBNET_NAME="$RUNNER_SUBNET_NAME"
export ARC_NODE_SKU="$NODE_SKU"
export ARC_SYSTEM_NODE_COUNT="$SYSTEM_NODE_COUNT"

"$ROOT_DIR/scripts/preflight.sh"

case "$1" in
  what-if)
    az deployment sub what-if \
      --name "$DEPLOYMENT_NAME" \
      --location "$LOCATION" \
      --template-file "$ROOT_DIR/infrastructure/main.bicep" \
      --parameters "$ROOT_DIR/infrastructure/main.bicepparam" \
      "${PARAMETER_OVERRIDES[@]}"
    ;;
  apply)
    az deployment sub create \
      --name "$DEPLOYMENT_NAME" \
      --location "$LOCATION" \
      --template-file "$ROOT_DIR/infrastructure/main.bicep" \
      --parameters "$ROOT_DIR/infrastructure/main.bicepparam" \
      "${PARAMETER_OVERRIDES[@]}"
    ;;
  *)
    usage
    exit 2
    ;;
esac
