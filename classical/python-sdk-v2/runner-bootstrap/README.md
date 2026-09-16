# Private AKS + ARC bootstrap

This directory bootstraps the **runner control plane only**. It deliberately does
not deploy the Azure Machine Learning workload. The steady-state workload remains
keyless through the existing GitHub Environment OIDC configuration; the GitHub App
below is a separate, repository-scoped credential used only by ARC to register
ephemeral runners.

## Fixed DEV shape

| Setting | Value |
| --- | --- |
| Existing hub VNet | `vnet-mlops-hub-dev-eus2-001` (`10.240.0.0/16`) |
| Runner subnet | `snet-github-runners` (`10.240.2.0/24`) |
| AKS | private control plane, Azure CNI Overlay, Azure RBAC |
| AKS identity | precreated user-assigned control-plane identity |
| System pool | 2 x `Standard_D2ads_v6` (4 vCPUs total; quota checked in `eastus2`) |
| Egress | dedicated Standard NAT Gateway/public IP |
| ARC chart | `0.14.2` |
| Runner base image | `ghcr.io/actions/actions-runner:2.337.0` |
| Runner tools | Python 3 and pinned Azure CLI `2.90.0-1~noble` |
| Scale set / workflow label | `mlops-private` |
| Runner bounds | minimum 0, maximum 2 |
| Logs | Container Insights and selected AKS control-plane logs, 30 days |

Both AKS system nodes are always billable even when ARC has zero idle runners.
Budget for two VMs (4 vCPUs total), the control plane, NAT Gateway/public IP, and
Log Analytics. The runner cap bounds workload concurrency, not these fixed costs.

## Hard gates

Do not run `provision.sh apply` until all of these are true:

1. A dedicated GitHub App is created and installed **only** on the target
   repository, and its verified App ID, installation ID, and private-key path are
   recorded in the local metadata file consumed by `install_arc.sh`.
2. The `Standard_D2ads_v6` regional restriction and vCPU quota checks remain clear.
3. `10.240.2.0/24` is unused, or the existing `snet-github-runners` has that
   exact prefix, no delegation, and compatible network-policy state.
4. The generated consumer provenance remains pinned to the reviewed factory,
   project-template, and reusable-template commits in `.mlops-generation.json`.
5. The workload configuration uses `runner_hub_vnet_resource_id` and explicitly
   chooses `manage_runner_hub_to_workload_peering`; workload deployment remains
   blocked until reciprocal routing and workload private DNS links exist.
6. The operator accepts the NAT egress IP, maximum concurrency of 2, and external
   Log Analytics retention/cost.
7. The tooling-only GHCR runner image is public, anonymously pullable, and supplied
   to `install_arc.sh` by immutable digest.
8. `ARC_OPERATOR_PRINCIPAL_OBJECT_ID` is the Microsoft Entra object ID of the
   GitHub OIDC service principal used by the update workflow. Resolve it from
   the configured client ID with
   `az ad sp show --id <client-id> --query id -o tsv`.

## Repository-scoped GitHub App

Use the approved GitHub App process documented in the project README. The App must
request only repository `Administration: write` and `Metadata: read`, with webhooks
disabled. Do not substitute a PAT. Store the PEM outside the checkout with mode
`0600`, and create `~/.config/mlops-project-arc/app.json` with `app_id`,
`installation_id`, and `pem_path`. Do not copy that state into this repository.

## Publish the runner image

The generated infrastructure workflows run Python and Azure CLI commands. The
stock ARC image does not contain those tools, so ARC installation fails closed
unless `ARC_RUNNER_IMAGE` names the approved image by immutable digest. The image
does not include an in-cluster container image builder. Non-root Kaniko runtime
builds are unsupported under the enforced security policy because the executor
attempts `chown /` and fails with `operation not permitted`; do not add
privilege, a Docker socket, or a replacement builder to work around that policy.

`Build private runner image` uses a GitHub-hosted runner with only
`contents: read` and `packages: write`. The Dockerfile's
`org.opencontainers.image.source` label links the package to this repository.
Because `workflow_dispatch` files must exist on the default branch, use this
sequence:

1. Complete review and merge this PR so the build and smoke workflows exist on
   `main`.
2. Dispatch `Build private runner image` on `main`. A new GHCR package defaults
   to private, so the first run publishes the image and then fails its anonymous
   pull check with links to the personal-account and organization package
   settings.
3. In the package settings, change this tooling-only container package to
   **Public**. GitHub does not expose a supported REST or GraphQL visibility
   mutation, so this is an explicit one-time package-administrator prerequisite.
4. Rerun `Build private runner image`. The workflow uses an empty temporary
   Docker configuration to inspect the immutable digest without credentials and
   fails closed unless anonymous access succeeds.
5. Copy the `ghcr.io/<owner>/<repository>-arc-runner@sha256:...` value from
   the successful workflow summary. `install_arc.sh` repeats the anonymous pull
   check from AKS and verifies `git`, `curl`, Python, Azure CLI, and the absence
   of `/var/run/docker.sock` before installing ARC.

Do not use a PAT, an expiring GitHub App installation token, or a mutable image tag
as an image pull credential.

After any runner Dockerfile change, rebuild on `main`, review the reported GHCR
digest, and rerun `install_arc.sh` with that new immutable
`ARC_RUNNER_IMAGE`. This performs a rolling ARC scale-set update without adding
registry credentials or mutable tags. Run `verify.sh` and the private runner
smoke test before dispatching private infrastructure or model workflows. Do not
patch generated workflows to install Docker, Buildah, Kaniko, or any other
builder with `apt-get` or `sudo`; rebuild and redeploy the reviewed runner image
instead. Azure ML curated MLflow no-code online inference is the generated
serving default and requires no custom runtime build. Immutable image-only
online deployment remains available only when an approved external image supply
chain provides the complete environment name, version, and digest-pinned image.

For later runner image rollouts, configure the DEV GitHub Environment variable
`ARC_AKS_CLUSTER_RESOURCE_ID` with the immutable resource ID of the private
runner AKS cluster and dispatch `Update private runner image` with the new
digest-pinned GHCR URI. Both jobs run on GitHub-hosted runners and use Azure Run
Command, so a broken or unpullable current ARC image cannot block recovery. The
first job updates the scale set; the reconciliation job waits for active
ephemeral runner sets to drain, removes stale generations, and verifies the
configured image. The update resolves the unique container named `runner`,
generates a one-operation JSON Patch for only that container's `image` field,
and reads the resource back to require the exact immutable digest. It fails
closed if the runner container is missing, duplicated, or has a nonnumeric
array index. It does not read Helm release Secrets or grant secret access.
Every AKS Run Command response must report both `provisioningState: Succeeded`
and `exitCode: 0`. Azure CLI process success alone is not accepted, and remote
commands use POSIX `set -eu` because AKS Run Command executes them with
`/bin/sh`. Temporary resource and JSON Patch files are removed by a remote exit
trap.

If an update failed before the remote command ran, fix the workflow and dispatch
it again with the same immutable image. Do not restart the ARC listener or
controller: the runner resource and generations did not change.

## Review and deploy

Review the subscription-scope deployment before creating billable resources:

```bash
az account set --subscription <subscription-id>
az deployment sub validate \
  --location eastus2 \
  --template-file runner-bootstrap/infrastructure/main.bicep \
  --parameters runner-bootstrap/infrastructure/main.bicepparam
runner-bootstrap/scripts/provision.sh what-if
```

`provision.sh` always runs `preflight.sh` first. Both scripts resolve location,
hub VNet/subnet, node SKU, and system-node count from the same configuration.
After the committed bicepparam file, `provision.sh` passes those exact validated
values as explicit deployment parameter overrides, so what-if/apply cannot deploy
different capacity or networking than preflight checked. The shared defaults match
`main.bicepparam`; use `LOCATION`, `ARC_HUB_RESOURCE_GROUP`, `ARC_HUB_VNET`,
`ARC_RUNNER_SUBNET_NAME`, `ARC_RUNNER_SUBNET_PREFIX`, `ARC_NODE_SKU`, and
`ARC_SYSTEM_NODE_COUNT` for intentional overrides.

The preflight verifies the exact subscription, subnet containment/non-overlap, SKU
restrictions, and regional plus exact VM-family vCPU headroom without creating
resources. It accepts an existing Bicep-owned runner subnet only when its name,
prefix, delegation, and network-policy state match, so repeat what-if/apply remains
idempotent.

Bicep creates a user-assigned AKS control-plane identity before the cluster and
grants it `Network Contributor` only on `snet-github-runners` using a deterministic
role-assignment GUID. The AKS module depends on that assignment and uses the
identity explicitly. The bootstrap operator therefore needs permission to create
role assignments at the runner-subnet scope.

After all hard gates are approved:

```bash
export ARC_RUNNER_IMAGE="ghcr.io/<owner>/<repository>-arc-runner@sha256:<digest>"
export ARC_GITHUB_CONFIG_URL="https://github.com/<owner>/<repository>"
export ARC_OPERATOR_PRINCIPAL_OBJECT_ID="<github-oidc-service-principal-object-id>"
export GITHUB_REPOSITORY="<owner>/<repository>"
runner-bootstrap/scripts/provision.sh apply
runner-bootstrap/scripts/install_arc.sh
runner-bootstrap/scripts/verify.sh
```

`install_arc.sh` uploads the local PEM directly to AKS Run Command, creates the
Kubernetes secret in `arc-runners`, and suppresses the secret-creation response.
The committed Helm values reference only the secret name. The privileged initial
install also applies an idempotent namespace Role and RoleBinding for the OIDC
service principal. That identity can only get and patch
`actions.github.com/autoscalingrunnersets`; get, list, and delete
`actions.github.com/ephemeralrunnersets`; and get, list, and delete core pods in
`arc-runners`. It cannot read Secrets, use `pods/exec`, access nodes, or mutate
Roles, RoleBindings, or service accounts. Do not replace this native Kubernetes
allowlist with Azure built-in Writer/Admin roles or preview ABAC.

The committed Helm values retain repository and image placeholders. The install
script validates that the immutable GHCR digest belongs to the configured GitHub
repository, renders a temporary values file, and retains the runner container
name, image, resource requests/limits, security contexts, and explicit
`/home/runner/run.sh` command. It verifies anonymous image pull and required tools
inside AKS and deletes the temporary file on exit. No mutable or live digest is
committed.

## Network validation

Before workload deployment, `verify.sh` checks controller/listener state and DNS/TLS
egress to GitHub, GHCR, Microsoft Entra, Azure Resource Manager, and PyPI. After the
workload VNet is deployed and peered, additionally resolve and reach the actual AML,
Storage (`blob`, `file`, `queue`, `table`, and `dfs`), Key Vault, and ACR private
endpoint hostnames from a runner pod. Each must resolve to a private address.

Prove autoscaling by manually dispatching `Private runner smoke test`, a harmless
`mlops-private` job committed at `.github/workflows/runner-smoke-test.yml`, with
the expected immutable runner image URI. The workflow checks out the shared
strict AKS Run Command helper, verifies the live pod image from the helper's
validated log output, and then tests the runner tools and egress. It does not
parse `az aks command invoke --query logs --output tsv` directly. Observe zero
ephemeral runner pods, one pod while the job runs, and zero after the job and ARC
cleanup complete. Only then dispatch infrastructure validation.

## Cleanup

Cleanup order matters:

1. Stop dispatching and wait for runner jobs to finish.
2. Run `runner-bootstrap/scripts/uninstall.sh arc`.
3. Delete the AKS runner resource group after reviewing dependencies.
4. Remove only `snet-github-runners` from the shared hub VNet after AKS deletion.
5. Revoke/delete the GitHub App installation and securely delete the local state.

Never delete the shared hub VNet, delegated MDP subnet, private-endpoint subnet, or
the existing workload OIDC app/service principal/RBAC assignments.
