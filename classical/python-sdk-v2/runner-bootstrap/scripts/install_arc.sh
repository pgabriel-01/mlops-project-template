#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INVOKE_AKS=(python3 "$ROOT_DIR/scripts/invoke_aks_command.py")
STATE_DIR=${ARC_APP_STATE_DIR:-"$HOME/.config/mlops-project-arc"}
METADATA_PATH=${ARC_APP_METADATA:-"$STATE_DIR/app.json"}
RESOURCE_GROUP=${ARC_RESOURCE_GROUP:-rg-mlops-arc-dev-eus2-001}
AKS_NAME=${ARC_AKS_NAME:-aks-mlops-arc-dev-eus2-001}
CHART_VERSION=0.14.2
CONTROLLER_NAMESPACE=arc-systems
RUNNER_NAMESPACE=arc-runners

[[ -n ${ARC_RUNNER_IMAGE:-} ]] || {
  echo "ARC_RUNNER_IMAGE is required and must use an immutable @sha256: digest" >&2
  exit 1
}
[[ -n ${ARC_GITHUB_CONFIG_URL:-} ]] || {
  echo "ARC_GITHUB_CONFIG_URL is required, for example https://github.com/owner/repository" >&2
  exit 1
}
RENDERED_VALUES=$(mktemp)
trap 'rm -f "$RENDERED_VALUES"' EXIT
python3 "$ROOT_DIR/scripts/render_runner_values.py" \
  "$ROOT_DIR/helm/runner-set-values.yaml" \
  "$RENDERED_VALUES" \
  --image "$ARC_RUNNER_IMAGE" \
  --github-config-url "$ARC_GITHUB_CONFIG_URL"

[[ -f "$METADATA_PATH" ]] || { echo "Missing verified App metadata: $METADATA_PATH" >&2; exit 1; }
APP_VALUES=$(python3 - "$METADATA_PATH" <<'PY'
import json, os, stat, sys
with open(sys.argv[1]) as stream:
    value = json.load(stream)
for key in ("app_id", "installation_id", "pem_path"):
    if not value.get(key):
        raise SystemExit(f"Missing {key} in verified GitHub App metadata")
pem = os.path.expanduser(value["pem_path"])
mode = stat.S_IMODE(os.stat(pem).st_mode)
if mode & 0o077:
    raise SystemExit(f"Private key permissions must be 0600 or stricter, got {mode:04o}")
print(f'{value["app_id"]}\t{value["installation_id"]}\t{pem}')
PY
)
IFS=$'\t' read -r APP_ID INSTALLATION_ID PEM_PATH <<<"$APP_VALUES"

command="set -eu; cleanup() { kubectl delete pod arc-image-pull-check --ignore-not-found >/dev/null 2>&1 || true; }; trap cleanup EXIT; cleanup; kubectl run arc-image-pull-check --image='$ARC_RUNNER_IMAGE' --restart=Never --command -- sh -ec 'git --version && curl --version && python3 --version && az version && test -x /kaniko/executor && test -w /kaniko && /kaniko/executor version && test ! -S /var/run/docker.sock'; kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/arc-image-pull-check --timeout=300s; kubectl logs arc-image-pull-check"
"${INVOKE_AKS[@]}" --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" \
  --command "$command" \
  --print-logs

command="kubectl create namespace $RUNNER_NAMESPACE --dry-run=client -o yaml | kubectl apply -f - && kubectl -n $RUNNER_NAMESPACE create secret generic arc-github-app --from-literal=github_app_id='$APP_ID' --from-literal=github_app_installation_id='$INSTALLATION_ID' --from-file=github_app_private_key=$(basename "$PEM_PATH") --dry-run=client -o yaml | kubectl apply -f -"
"${INVOKE_AKS[@]}" --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" \
  --command "$command" \
  --file "$PEM_PATH"

"${INVOKE_AKS[@]}" --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" \
  --command "helm upgrade --install arc --namespace $CONTROLLER_NAMESPACE --create-namespace --version $CHART_VERSION -f controller-values.yaml oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller" \
  --file "$ROOT_DIR/helm/controller-values.yaml" \
  --print-logs

"${INVOKE_AKS[@]}" --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" \
  --command "helm upgrade --install mlops-private --namespace $RUNNER_NAMESPACE --create-namespace --version $CHART_VERSION -f $(basename "$RENDERED_VALUES") oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set" \
  --file "$RENDERED_VALUES" \
  --print-logs

echo "ARC $CHART_VERSION installed. Run verify.sh before dispatching any workload."
