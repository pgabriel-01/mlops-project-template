#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/deployment_config.sh"

ACTIVE_SUBSCRIPTION=$(az account show --query id -o tsv)
[[ "$ACTIVE_SUBSCRIPTION" == "$SUBSCRIPTION_ID" ]] || {
  echo "Active subscription is $ACTIVE_SUBSCRIPTION; expected $SUBSCRIPTION_ID" >&2
  exit 1
}

VNET_JSON=$(az network vnet show \
  --resource-group "$HUB_RESOURCE_GROUP" \
  --name "$HUB_VNET" \
  --query '{addressPrefixes:addressSpace.addressPrefixes,subnets:subnets[].{name:name,prefix:addressPrefix,delegations:delegations[].serviceName,privateEndpointNetworkPolicies:privateEndpointNetworkPolicies,privateLinkServiceNetworkPolicies:privateLinkServiceNetworkPolicies}}' \
  -o json)

python3 "$SCRIPT_DIR/validate_runner_subnet.py" \
  "$RUNNER_SUBNET_PREFIX" \
  "$RUNNER_SUBNET_NAME" \
  "$VNET_JSON"

SKU_JSON=$(az vm list-skus \
  --location "$LOCATION" \
  --size "$NODE_SKU" \
  --resource-type virtualMachines \
  --all \
  -o json)
USAGE_JSON=$(az vm list-usage --location "$LOCATION" -o json)

python3 "$SCRIPT_DIR/validate_compute_quota.py" \
  "$NODE_SKU" \
  "$SYSTEM_NODE_COUNT" \
  "$SKU_JSON" \
  "$USAGE_JSON"

echo "Preflight passed for $NODE_SKU in $LOCATION"
