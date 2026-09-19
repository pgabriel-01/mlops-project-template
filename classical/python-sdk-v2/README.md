# Classical ML project pattern

This repository is a focused Azure Machine Learning project generated for:

- Python SDK v2 workload automation;
- GitHub Actions with GitHub Environment-based OIDC;
- Bicep infrastructure;
- managed online and batch inference.

It intentionally excludes alternate IaC engines, legacy command-based workload
definitions, and non-GitHub pipeline systems.

## Deployment contract

Create GitHub Environments named `dev`, `test`, and `prod`. Each environment must
provide these environment-scoped secrets:

| Secret | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID of the environment's federated workload identity |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription |

Each environment must also define the environment-scoped variable
`AZURE_PRINCIPAL_OBJECT_ID`, containing the service principal object ID used for
idempotent Bicep role assignments.

Configure the workload identity federation with:

- issuer: `https://token.actions.githubusercontent.com`;
- audience: `api://AzureADTokenExchange`;
- DEV subject: `repo:<owner>/<repo>:environment:dev`;
- Test subject: `repo:<owner>/<repo>:environment:test`;
- Prod subject: `repo:<owner>/<repo>:environment:prod`.

No client secret or legacy Azure credentials JSON secret is created or used.

### Azure bootstrap

The bootstrap operator must be allowed to create Microsoft Entra applications and
service principals. Set the generic placeholders below, sign in with Azure CLI,
and run the script. It reuses an existing application, service principal,
federated credentials, and role assignments when present.

The CI principal needs `Contributor` and `Role Based Access Control Administrator`
at `/subscriptions/<subscription-id>`. This is preferred over `Owner`:
`Contributor` deploys resources, while `Role Based Access Control Administrator`
permits the Bicep modules to create their required role assignments.

```bash
export APP_NAME="<federated-application-name>"
export GITHUB_OWNER="<owner>"
export GITHUB_REPOSITORY="<repo>"
export AZURE_SUBSCRIPTION_ID="<subscription-id>"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
AZURE_TENANT_ID="$(az account show --query tenantId -o tsv)"
SUBSCRIPTION_SCOPE="/subscriptions/$AZURE_SUBSCRIPTION_ID"

AZURE_CLIENT_ID="$(
  az ad app list \
    --display-name "$APP_NAME" \
    --query "[0].appId" \
    -o tsv
)"
if [ -z "$AZURE_CLIENT_ID" ]; then
  AZURE_CLIENT_ID="$(
    az ad app create \
      --display-name "$APP_NAME" \
      --query appId \
      -o tsv
  )"
fi

APP_OBJECT_ID="$(az ad app show --id "$AZURE_CLIENT_ID" --query id -o tsv)"
AZURE_PRINCIPAL_OBJECT_ID="$(
  az ad sp list \
    --filter "appId eq '$AZURE_CLIENT_ID'" \
    --query "[0].id" \
    -o tsv
)"
if [ -z "$AZURE_PRINCIPAL_OBJECT_ID" ]; then
  AZURE_PRINCIPAL_OBJECT_ID="$(
    az ad sp create --id "$AZURE_CLIENT_ID" --query id -o tsv
  )"
fi

for ENVIRONMENT in dev test prod; do
  CREDENTIAL_NAME="github-${ENVIRONMENT}"
  SUBJECT="repo:${GITHUB_OWNER}/${GITHUB_REPOSITORY}:environment:${ENVIRONMENT}"
  CREDENTIAL_FILE="$(mktemp)"
  cat > "$CREDENTIAL_FILE" <<EOF
{
  "name": "$CREDENTIAL_NAME",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "$SUBJECT",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

  CREDENTIAL_ID="$(
    az ad app federated-credential list \
      --id "$APP_OBJECT_ID" \
      --query "[?name=='$CREDENTIAL_NAME'].id | [0]" \
      -o tsv
  )"
  if [ -z "$CREDENTIAL_ID" ]; then
    az ad app federated-credential create \
      --id "$APP_OBJECT_ID" \
      --parameters "@$CREDENTIAL_FILE"
  else
    az ad app federated-credential update \
      --id "$APP_OBJECT_ID" \
      --federated-credential-id "$CREDENTIAL_ID" \
      --parameters "@$CREDENTIAL_FILE"
  fi
  rm -f "$CREDENTIAL_FILE"
done

for ROLE_ID in \
  "b24988ac-6180-42a0-ab88-20f7382dd24c" \
  "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
do
  ASSIGNMENT_ID="$(
    az role assignment list \
      --assignee-object-id "$AZURE_PRINCIPAL_OBJECT_ID" \
      --scope "$SUBSCRIPTION_SCOPE" \
      --role "$ROLE_ID" \
      --query "[0].id" \
      -o tsv
  )"
  if [ -z "$ASSIGNMENT_ID" ]; then
    az role assignment create \
      --assignee-object-id "$AZURE_PRINCIPAL_OBJECT_ID" \
      --assignee-principal-type ServicePrincipal \
      --scope "$SUBSCRIPTION_SCOPE" \
      --role "$ROLE_ID"
  fi
done
```

Verify that both assignments exist directly at the subscription scope:

```bash
az role assignment list \
  --assignee-object-id "$AZURE_PRINCIPAL_OBJECT_ID" \
  --scope "$SUBSCRIPTION_SCOPE" \
  --query "[?scope=='$SUBSCRIPTION_SCOPE' && (roleDefinitionName=='Contributor' || roleDefinitionName=='Role Based Access Control Administrator')].{role:roleDefinitionName,scope:scope}" \
  -o table
```

This verification intentionally omits `--include-inherited false`. Some Azure CLI
versions reject that boolean form, so the JMESPath expression filters the result
to assignments whose `scope` exactly equals `$SUBSCRIPTION_SCOPE`.

Create the GitHub Environments, then store the OIDC coordinates in each
environment rather than as repository-wide values:

```bash
for ENVIRONMENT in dev test prod; do
  gh secret set AZURE_CLIENT_ID \
    --env "$ENVIRONMENT" \
    --body "$AZURE_CLIENT_ID"
  gh secret set AZURE_TENANT_ID \
    --env "$ENVIRONMENT" \
    --body "$AZURE_TENANT_ID"
  gh secret set AZURE_SUBSCRIPTION_ID \
    --env "$ENVIRONMENT" \
    --body "$AZURE_SUBSCRIPTION_ID"
  gh variable set AZURE_PRINCIPAL_OBJECT_ID \
    --env "$ENVIRONMENT" \
    --body "$AZURE_PRINCIPAL_OBJECT_ID"
done
```

Environment settings live in `config-infra-dev.yml`, `config-infra-test.yml`, and
`config-infra-prod.yml`. The default private-network configuration uses the
`mlops-private` runner label; register an approved self-hosted runner with that
label and network/DNS access to the private endpoints, or replace it with a label
approved by your organization. Do not switch a private deployment to a
GitHub-hosted runner unless it has an explicit network path to the resources.
The private runner must be online and assigned this label before any infrastructure
validation, deployment, training, or endpoint workflow is dispatched.

### Autoscaling private runner prerequisite

For a private deployment, bootstrap a dedicated private Azure Kubernetes Service
(AKS) cluster and a GitHub Actions Runner Controller (ARC) runner scale set before
running this project. The AKS/ARC/GitHub App stack is a separate platform
prerequisite: these MLOps workflows must not attempt to create, upgrade, repair, or
delete the runner infrastructure that they require in order to execute.

The generated `runner-bootstrap/` assets provide the reviewed GitHub Actions,
Helm, shell, Python, and Bicep implementation for that separately operated
platform. Its default system pool is 2 x `Standard_D2ads_v6` (4 vCPUs total), which
preserves control-plane headroom after the ARC controller and listener are
installed. Both nodes and the accompanying control plane, NAT, public IP, and log
retention are fixed costs even when `minRunners` is zero. The runner pod template
also invokes `/home/runner/run.sh` explicitly so the custom runner image cannot
exit successfully before registering for work.

Use `mlops-private` as the ARC runner scale-set name/label, or update `runner` in
all environment configuration files to the chosen scale-set label. Steady-state
infrastructure, training, and endpoint jobs resolve `runs-on` to that label and
are scheduled onto ephemeral ARC runner pods.

To connect an existing runner hub VNet, set these environment configuration
fields. Leave the defaults unchanged for deployments that do not use a shared
runner hub:

```yaml
runner_hub_vnet_resource_id: "/subscriptions/<runner-subscription-id>/resourceGroups/<runner-network-resource-group>/providers/Microsoft.Network/virtualNetworks/<runner-hub-vnet>"
manage_runner_hub_to_workload_peering: false
```

When `runner_hub_vnet_resource_id` is nonempty, Bicep owns the deterministic
workload-to-hub peering and runner-hub links for every generated private DNS zone.
Those zones cover Azure Machine Learning API and notebooks, Storage blob, file,
queue, table, and DFS, Key Vault, and Azure Container Registry. The same runner
hub VNet must not be linked to these deployment-owned zones or peered to the
workload VNet under separately chosen names by another deployment.

Reciprocal peering has an explicit ownership boundary:

- With `manage_runner_hub_to_workload_peering: false` (the default), the runner
  platform owner owns the hub-to-workload peering. The subscription deployment
  outputs an exact idempotent `az network vnet peering create` command using the
  canonical deterministic peering name. Run that operation from the separately
  owned runner-platform process.
- With `manage_runner_hub_to_workload_peering: true`, this Bicep deployment owns
  both peering directions. Its OIDC principal needs `Network Contributor` or an
  equivalent custom role at the runner hub VNet scope, including cross-subscription
  scope when applicable. Hub-scope join permission is also required for the
  deployment-owned private DNS links.

Choose one reciprocal owner and keep it stable. Do not enable Bicep ownership when
a differently named hub-to-workload peering already exists; remove or import the
old ownership first. Empty/false defaults preserve the standalone generated
topology.

If the runner hub is already linked to authoritative private DNS zones for any
of those namespaces, reuse every matching zone instead of creating conflicting
second hub links. Set `shared_private_dns_zone_resource_ids` to a JSON object
whose keys are the exact zone names and whose values are full zone resource IDs,
for example:

```yaml
shared_private_dns_zone_resource_ids: "{\"privatelink.blob.core.windows.net\":\"/subscriptions/<subscription-id>/resourceGroups/<dns-resource-group>/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net\"}"
```

The map must include every supported namespace already linked to the runner hub,
not only Blob. Each supplied zone must already be linked to that hub. The
fail-closed infrastructure preflight queries all Azure subscriptions visible to
the deployment identity and rejects omitted, mismatched, unlinked, or duplicate
authoritative zones before ARM validation or deployment. Bicep skips creating
runner-hub links for supplied zones, links the workload VNet to each shared zone,
and uses those zones for private endpoint DNS zone groups so records remain
resolvable from both networks. Supported namespaces with no existing hub link
remain deployment-owned. Empty runner-hub settings preserve standalone behavior
and do not query Azure.

Key Vault naming is also bounded deterministically: the generated name uses a
normalized five-character project prefix, the 13-character resource-group hash,
and a three-character environment suffix, including the `kv-` prefix in Azure's
24-character maximum. The full resource-group identity remains in the hash so
truncating the readable prefix does not remove deployment uniqueness.

The runner network must satisfy all of these conditions before deployment:

- use non-overlapping address spaces and bidirectional routing between the runner
  VNet and each generated workload VNet, with the required forwarded-traffic,
  route-table, firewall, and NSG rules;
- when using the Bicep integration above, verify its links to the workload private
  DNS zones for Azure Machine Learning (`privatelink.api.azureml.ms` and
  `privatelink.notebooks.azure.net`), Storage (`privatelink.blob`,
  `privatelink.file`, `privatelink.queue`, `privatelink.table`, and
  `privatelink.dfs` for the active Azure cloud suffix), Key Vault
  (`privatelink.vaultcore.azure.net`), and Azure Container Registry
  (`privatelink.azurecr.io`);
- verify private DNS resolution and TCP connectivity from an ARC runner pod, not
  only from the AKS node or an administrator workstation;
- allow controlled outbound DNS and HTTPS for GitHub registration and actions
  downloads, including the GitHub API and the GitHub-hosted content endpoints
  required by ARC and actions;
- allow controlled outbound HTTPS to Microsoft Entra ID and the Azure control
  plane, plus the Azure Machine Learning service endpoints used by the SDK;
- allow the package feeds and registries required by the pinned workload, such as
  Python package feeds, Microsoft Container Registry, and the generated private
  Azure Container Registry.

Maintain these egress allowances with the organization's firewall or proxy policy
and the current GitHub, Azure, and package-provider endpoint documentation. The
runner platform requires no public inbound management path: prefer a private AKS
API endpoint and administer it through an approved private management path.

ARC registration must use a dedicated GitHub App installed only on the target
repository or organization. Grant only the permissions required by the selected
scope: repository administration read/write plus metadata read for a
repository-scoped runner group, or organization self-hosted runners read/write
plus metadata read for an organization-scoped runner group. Store the GitHub App
ID, installation ID, and private key in a Kubernetes Secret or approved external
secret provider in the runner cluster. Do not store the private key, a GitHub PAT,
or a GitHub App client secret in this repository, its reusable workflows, or the
generated project. GitHub App authentication controls ARC runner registration
only; Azure workload access continues to use the environment-scoped OIDC contract

### Private Azure ML managed online inference

The supported real-time serving path is a private Azure ML managed online
endpoint. The workspace private endpoint provides private scoring ingress, the
endpoint disables public network access, and callers use Microsoft Entra
`aad_token` authentication. The workspace uses managed network v1 with
`AllowOnlyApprovedOutbound`; Azure ML creates the default managed private
endpoint rules for the associated Storage, ACR, and Key Vault resources.

The stable generated-workflow contract is:

- `enable_managed_online_endpoint: true`;
- `online_mlflow_no_code: true`: Azure ML supplies the curated environment for
  the validated MLflow model; the environment name, version, and image settings
  must all be empty;
- `online_mlflow_no_code: false`: immutable image-only compatibility mode, which
  requires `online_environment_name`, `online_environment_version`, and a private
  ACR `online_environment_image` pinned by SHA-256 digest, plus
  `online_code_directory` and `online_scoring_script`;
- `online_deployment_name` and `online_alternate_deployment_name`: fixed
  blue-green slots;
- `online_traffic_percentage`: validated candidate traffic after the private
  smoke test;
- `online_instance_type`: managed endpoint Azure VM SKU;
- `online_instance_count`: explicit deployment capacity;
- `runner`: private ARC runner label.

The generated MLflow no-code path does not create a workspace environment and
does not build a custom runtime image. Azure ML resolves its curated MLflow
serving environment from the registered MLflow model. Non-root Kaniko execution
is not a supported fallback under the runner security policy because it attempts
to change ownership at the container root and fails with `chown /: operation not
permitted`. The generated pattern therefore contains no runtime image publishing
workflow or custom online runtime Dockerfile, and it does not weaken the
non-root, unprivileged runner contract. Organizations that already operate an
approved external image supply chain can select image-only mode and provide the
complete immutable environment triple directly. The workflow provisions the
workspace managed network, creates the endpoint and deployment with Python SDK
v2, invokes the named deployment privately, and promotes traffic only after the
deployment reports success.

Online releases use fixed `blue` and `green` deployment slots. The workflow
updates only the slot that is not currently serving the previous model, performs
the private smoke invocation against that candidate, and changes the configured
traffic percentage afterward. A deterministic fingerprint covers the model,
environment/image, scoring-code contents, capacity, probes, request settings,
and telemetry configuration; an active slot is reused only when the full
fingerprint matches. The previous deployment remains available for rollback. The equivalent
Azure DevOps pipeline requires an explicitly configured private self-hosted
Linux pool and workload identity federation; Microsoft-hosted agents are
rejected because they cannot resolve or route to the private endpoint.

Both orchestrators serialize endpoint changes through the same
Entra-authenticated, endpoint-scoped blob lease in the private workspace storage
account. The lease renews while deployment is active, releases in cleanup, and
expires automatically after a terminated runner stops renewing it.

The generated `update-runner-image.yml` accepts only this repository's immutable
GHCR runner digest and targets the AKS resource ID configured in the DEV GitHub
Environment variable `ARC_AKS_CLUSTER_RESOURCE_ID`. Its shared AKS Run Command
wrapper rejects remote nonzero `exitCode` values even when Azure CLI exits zero,
prints sanitized logs only on failure, and uses POSIX remote shell options. The
image update dynamically resolves exactly one container named `runner`, applies
a one-operation JSON Patch only to its `image` field, and verifies the exact
immutable digest by reading the resource back. It does not read Helm release
Secrets or expand the OIDC principal's secret access.

The AKS cluster remains a separately operated ARC platform prerequisite. It has
no AML Kubernetes extension, AML compute attachment, inference node pool, or
scoring DNS/TLS responsibility. ARC controller, listener, and runner pods are
ephemeral managed workloads and are prohibited for interactive administration.

The optional private Linux `Dev jumpbox` is enabled by default in Dev and
disabled by default in Test and Prod. Both the VM and Premium Bastion host have
no public IP. Entra SSH, scoped VM login roles, pinned Azure tooling, and
automatic shutdown/deallocation are enforced. Private-only Bastion is reachable
only from an administrator with an existing VPN, ExpressRoute, peering, or other
approved private routed path to the VNet; Azure Portal access from the public
internet does not provide that connectivity and no public-IP fallback is
created. The optional login group receives VM User Login plus Reader only on the
VM, its NIC, and the Bastion resource. Azure CLI, the system-wide pinned `az ml`
extension, and the isolated Azure ML Python SDK environment are installed for
human troubleshooting.

See `docs/private-managed-online-inference.md` for the complete deployment,
migration, rollback, DNS, and identity contract.

For a repository owned by a personal GitHub account, stop before provisioning AKS
until the owner confirms personal-repository GitHub App compatibility or migrates
the repository to an approved organization. The owner must select or create the
App, approve its exact permissions, install it only on the target repository,
record the App and installation IDs, store the one-time private key directly in
approved secret storage, and approve runner scale bounds, egress policy, and any
external log destinations. Do not substitute a PAT.

When creating a personal-account App through
`https://github.com/settings/apps/new`, use the manifest flow with:

- a loopback-only redirect URL, an unguessable `state` value, and exact callback
  validation before exchanging the temporary code;
- repository permissions `administration: write` and `metadata: read`;
- `hook_attributes.active: false`, `public: false`, no OAuth-on-install, and no
  subscribed events;
- the single-use manifest conversion endpoint
  `POST /settings/apps/{code}/conversions` within its one-hour validity window,
  without logging the response;
- the returned PEM written directly outside the checkout with permissions `0600`,
  then transferred to the approved Kubernetes or external secret store;
- unused client secrets and webhook secrets discarded, and installation access
  restricted to the target repository.

Set explicit ARC scale bounds. A zero-idle configuration can use `minRunners: 0`
with a positive `maxRunners`, reducing idle compute cost at the expense of pod and
node startup latency. Set `minRunners` above zero when predictable startup time is
more important than idle cost. Bound `maxRunners` to the AKS node-pool capacity,
Azure API throttling budget, and the maximum approved GitHub Actions concurrency;
also apply repository, environment, or workflow concurrency controls so queued
work cannot exceed that operational limit.

Keep runner and workload lifecycles separate. For cleanup:

1. stop new workflow dispatches and let in-progress jobs finish;
2. while at least one `mlops-private` runner is still online, run and verify any
   explicit workload teardown, including deployment-owned DNS links and peerings;
   if the runner platform owns reciprocal peering, remove that peering through the
   same separate platform process after workload teardown;
3. cancel remaining queued jobs, set ARC runner scale bounds to zero, and wait for
   ephemeral runner pods to terminate and deregister;
4. uninstall the ARC runner scale set and controller, then remove their Kubernetes
   secrets;
5. delete the dedicated AKS and runner-network bootstrap only through its separate
   platform lifecycle.

All runner bootstrap examples and reusable files must retain generic placeholders.
Do not add a consumer repository name, tenant ID, subscription ID, resource ID, or
environment resource name to this project pattern.

## Workflows

Run these workflows in order for DEV:

1. `Deploy infrastructure` with `environment=dev`; validate first, then rerun with
   `deploy=true` after review.
2. `Train and register model`; retain the reported model version.
3. `Deploy and test online endpoint` with that model version.
4. `Deploy, invoke, and test batch endpoint` with that model version.

The same workflow inputs and configuration shape support `test` and `prod`.
Infrastructure validation runs on pull requests and does not deploy resources.

Reusable workflow references contain generator placeholders in this source
repository. Generation must replace both
`__MLOPS_TEMPLATES_REPOSITORY__` and `__MLOPS_TEMPLATES_REF__`, with the latter set
to an immutable commit SHA.

This repository does not contain a standalone project factory. The
`classical/python-sdk-v2` source pattern is maintained directly here, and
`tests/test_project_contract.py` assembles the documented generated layout to
verify each propagation. Do not describe a change as factory-regenerated unless
an external factory was actually used and recorded separately.

The reviewed reusable-workflow propagation is pinned in that contract to
`pgabriel-01/mlops-templates@812be5b654e974b573a0f5a52f2869068226a194`.
Generated Python SDK v2 workflows bind both the reusable workflow and its
checked-out SDK helpers to that same immutable ref. It supports MLflow no-code
online deployment while preserving the explicit immutable image-only mode. For
batch deployment, the pin applies the registry operation scope's validated full
ARM ID to the fetched `Environment` entity so Azure ML SDK dependency upload
extracts the supported value. It also waits for endpoint completion and
confirmed successful provisioning before deployment, waits for deployment
before invocation, retries boundedly when an existing operation conflicts, and
propagates terminal failures and timeouts. The batch caller exposes an immutable
deployment environment input that defaults to
`azureml://registries/azureml/environments/sklearn-1.5/versions/53`. The reusable
workflow validates that the value is a versioned Azure ML environment reference
with a numeric version and passes the full ID into `BatchDeployment`; mutable
labels, `latest`, unversioned references, images, and inline Conda definitions are
rejected before the Azure ML client is created. The generated caller also passes
the checked-in `mlops/azureml/deploy/batch/score.py` from a dedicated consumer
directory. The reusable helper constructs a non-null `CodeConfiguration`, then
reads the live deployment back and verifies both the immutable environment and
scoring configuration before defaulting or invoking the endpoint. This prevents
Azure ML from silently falling back to an anonymous Conda environment and
workspace-local image build, which is incompatible with the preserved
`allowSharedKeyAccess=false` storage policy.

Online deployment is repository-owned rather than delegated to the shared
template ref. It uses Azure ML Python SDK v2 managed endpoint entities, a
configured Azure VM SKU and instance count, the deterministic endpoint UAMI, and
an awaited private smoke invocation before traffic promotion. It does not attach
Kubernetes compute or permit an anonymous environment build path.
Set `VERIFY_REMOTE_TEMPLATES=1` when running the project contract to verify the
pinned AML client, training and batch workflows and helpers, sequencing tests,
scoring path and live deployment checks, failed-job diagnostics, immutable
diagnostics artifact upload, and batch environment contract directly from that
commit.

The generated training pipeline uses the immutable curated environment
`azureml://registries/azureml/environments/sklearn-1.5/versions/53` for prepare,
train, and evaluate. Keep the explicit version: `latest` is mutable, and inline
image plus conda definitions make the workspace image builder stage a revision
snapshot in workspace storage. Storage local authentication remains disabled by
policy, so generated jobs must use the reviewed prebuilt environment rather than
requiring that workspace-specific image-build path.

Private workspaces also set the ARM `imageBuildCompute` property from
`batch_compute_name` (default `cpu-cluster`). The workspace records the
deterministic compute name on its initial deployment, and the compute deployment
then depends on the workspace and its private endpoint. This avoids a circular
ARM dependency while ensuring later workspace-local image builds run on the
managed-network, no-public-IP cluster and can push through the workspace
identity's `AcrPush` assignment. Azure rejects a custom subnet on AmlCompute when
the workspace managed network is enabled, so the generated module omits its
custom subnet in that mode. The module still supports a custom subnet for
unmanaged-network workspace variants. No deployment script, registry shared key,
or public network exception is required.

First deployment is intentionally two-phase for managed-network workspaces.
Bicep first creates the workspace and target-scoped Azure AI Enterprise Network
Connection Approver assignments on Storage, Key Vault, ACR, and the AML
workspace itself, plus Reader at exactly the ACR scope because the approver role
does not include the registry read action. The workflow then invokes the supported
`az ml workspace provision-network` operation (omitting the presence-only
`--include-spark` flag) with bounded retries only for authorization propagation.
Compute is deployed only after that operation succeeds. This avoids the
first-deploy RBAC propagation race without granting Contributor, Owner, or
resource-group-wide access.

This propagation was applied directly to the maintained source pattern and its
assembled-tree contract; it was not produced by a standalone generator.

## Keyless private architecture

Bicep disables storage shared-key access, configures identity-authenticated system
datastores, and grants the workspace identity data-plane access. When private
networking is enabled, workspace public access is disabled and private endpoints
plus DNS zones connect the generated workload VNet to the workspace, registry,
vault, and storage blob, file, queue, table, and DFS services. The workspace uses
Managed Network V1 with `AllowOnlyApprovedOutbound`. Its AML compute cluster has
public node IPs disabled and no custom subnet, because Azure rejects
custom-subnet AmlCompute for a managed-network workspace. The workspace also
omits `serverlessComputeCustomSubnet`.

For private deployments, the AmlCompute module starts only after the conditional
workspace private endpoint module completes. This prevents no-public-IP compute
creation from racing the endpoint required by Azure. When VNet deployment is
disabled, ARM skips the conditional endpoint and its dependency, so public
compute creation remains valid.

This repository does not apply network changes automatically outside the explicit
infrastructure workflow.

## Local validation

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python mlops/scripts/validate_project.py
az bicep build --file infrastructure/bicep/main.bicep
```
