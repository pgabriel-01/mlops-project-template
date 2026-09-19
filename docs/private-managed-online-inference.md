# Private Azure ML managed online inference

The supported real-time inference path is an Azure Machine Learning managed
online endpoint. The private AKS cluster is reserved for GitHub Actions Runner
Controller (ARC) and is not attached to Azure ML as Kubernetes compute.

## Network and identity contract

- The Azure ML workspace sets `publicNetworkAccess=Disabled`,
  `v1LegacyMode=false`, and managed network v1 isolation to
  `AllowOnlyApprovedOutbound`.
- The workspace private endpoint and its
  `privatelink.api.azureml.ms` private DNS zone provide private access to the
  managed endpoint scoring URI. There is no endpoint-specific private endpoint,
  custom scoring DNS record, extension certificate, or CA bundle.
- Azure ML creates the managed-network private endpoint rules for the
  workspace-associated Storage account, ACR, and Key Vault. Add explicit
  outbound rules only for additional runtime dependencies.
- The workspace UAMI has the narrowly scoped Azure AI Enterprise Network
  Connection Approver role on those associated resources so Azure ML can approve
  the managed private endpoint connections.
- The endpoint uses a dedicated UAMI. It receives `AcrPull` and
  `Storage Blob Data Reader`; `Key Vault Secrets User` is opt-in and disabled by
  default.
- The OIDC deployment principal receives `Managed Identity Operator` only on the
  endpoint UAMI so it can attach that identity without broader identity
  management permissions.
- Infrastructure creates a private `deployment-locks` blob container in the
  workspace storage account. The CI principal receives Blob Data Contributor at
  that container scope for lease operations; shared-key access remains disabled.
- Endpoint callers authenticate with Microsoft Entra tokens
  (`auth_mode="aad_token"`). GitHub Actions authenticates to Azure by OIDC and
  stores no client secret.

The private runner must have routing and private DNS access to the workspace
private endpoint. OIDC authenticates the workflow but does not provide network
connectivity.

When the runner hub is already linked to authoritative private DNS zones, callers
must supply the full resource ID for every matching supported namespace through
`sharedPrivateDnsZoneResourceIds`; supplying only Blob is not sufficient. The
shared-zone map remains generic and may reference zones in any subscription
visible to the deployment identity. A fail-closed preflight compares the map to
the runner hub's actual links before both GitHub Actions and Azure DevOps
validation/deployment. Supplied zones skip duplicate runner-hub links while still
linking the workload VNet; callers without a shared runner hub retain the
standalone deployment behavior.

GitHub Actions and Azure DevOps acquire the same endpoint-scoped blob lease
before reading traffic or selecting a deployment slot. The renewable 60-second
lease is held through smoke validation and traffic promotion and released on
both success and failure. A competing deployment fails with a clear contention
message. If a runner terminates without cleanup, renewal stops and Azure releases
the stale lease after its duration; storage keys are never used.

## Deployment ordering

The online workflow uses pinned Azure ML Python SDK v2 tooling and performs these
steps synchronously:

1. Provision the workspace managed network with
   `az ml workspace provision-network`. Omit the presence-only `--include-spark`
   flag when Spark provisioning is not required.
2. Verify the workspace still disables public access, has
   `v1_legacy_mode=false`, and uses `AllowOnlyApprovedOutbound`. If the SDK
   normalizes the optional field to `None`, read the authoritative ARM property
   and require literal `false`.
3. Verify the requested model name and exact version exist in the target
   workspace before creating or updating endpoint resources.
4. Create or reconcile the managed endpoint with its fixed UAMI and no invalid
   traffic reference.
5. Select one of two fixed deployment slots (`blue` and `green`). A new model is
   deployed only to the slot that is not currently serving traffic; a rerun for
   the same complete deployment specification reuses its existing slot.
6. Create or reconcile the candidate deployment from an immutable model version
   and wait for provisioning to succeed.
7. Invoke the named candidate directly from the private runner.
8. Re-read the endpoint and promote the configured traffic percentage only
   after the smoke invocation succeeds. The previous deployment resource is
   retained for rollback.

Each deployment stores a deterministic fingerprint covering the immutable model,
environment/image, uploaded scoring-code contents, instance type/count, request
settings, probes, and telemetry setting. A slot receiving traffic is reusable
only when that complete fingerprint matches. Changing any rollout input,
including scoring code while retaining the same model version, selects the
inactive slot or fails closed when both slots are already serving traffic.

The endpoint UAMI cannot be changed in place. Replace the endpoint if its identity
contract changes.

The default MLflow no-code mode uses the registered MLflow model. Image-only mode
requires a complete environment name/version and a private ACR image pinned by
SHA-256 digest, plus a repository-owned code directory and scoring script.
Mutable image tags, missing scoring code, and partial definitions fail
validation.

The Azure DevOps online pipeline uses the same Python SDK v2 implementation. It
requires an explicitly selected private self-hosted Linux agent pool with VNet
routing/private DNS and an Azure service connection configured for workload
identity federation. Sentinel, Microsoft-hosted, or non-OIDC configurations fail
closed before deployment.

## Dev jumpbox

`Dev jumpbox` is an optional Linux administration VM. It is enabled by default
only in Dev and disabled by default in Test and Prod.

- The VM and Premium Bastion host have no public IP.
- The VM uses Entra SSH through `AADSSHLoginForLinux`, a system-assigned managed
  identity, password authentication disabled, and Trusted Launch.
- The repository contains a stable public-only SSH bootstrap key whose private
  key was discarded and is not retained. This keeps repeated ARM deployments
  idempotent while satisfying VM provisioning. Cloud-init removes the authorized
  key on first boot; routine and ongoing access is Entra-only.
- Azure CLI, the system-wide `az ml` extension, and Azure ML Python SDK versions
  are pinned. The extension is installed under `/opt/az-extensions` and exposed
  to all Entra SSH users through `AZURE_EXTENSION_DIR`.
- A daily DevTestLab schedule shuts down and deallocates the VM.
- An optional group receives `Virtual Machine User Login` at VM scope plus
  `Reader` at exactly the VM, its NIC, and the Bastion host scopes required by
  the Bastion native client. It receives no resource-group, subscription, or
  Contributor role. Administrator login should be granted through time-bound
  Entra PIM/JIT activation, not persistent Contributor access.

Private-only Bastion is reachable only after the administrator already has
private routed connectivity to the VNet, such as VPN, ExpressRoute, or an
approved peered private host. Azure Portal access from the public internet does
not provide that network path. Do not add a Bastion or VM public IP as a fallback.
The deployment outputs the Bastion resource ID, jumpbox VM resource ID, and
jumpbox private IP for private DNS and operations integration.

After establishing the approved private route, a group member can connect with
the Bastion native client:

```bash
az login
az account set --subscription <subscription-id>

RESOURCE_GROUP=<managed-resource-group>
BASTION_NAME=<private-bastion-name>
JUMPBOX_VM_ID=$(az vm show \
  --resource-group "$RESOURCE_GROUP" \
  --name <jumpbox-vm-name> \
  --query id \
  --output tsv)

az network bastion ssh \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BASTION_NAME" \
  --target-resource-id "$JUMPBOX_VM_ID" \
  --auth-type AAD
```

On the jumpbox, authenticate as the human operator rather than borrowing an ARC
runner identity, then verify the pinned tooling:

```bash
export AZURE_EXTENSION_DIR=/opt/az-extensions
az login --use-device-code
az account set --subscription <subscription-id>
az extension show --name ml --query version --output tsv
/opt/azureml-admin/bin/python -c \
  'import azure.ai.ml, azure.identity; print("Azure ML Python SDK ready")'
az ml workspace show \
  --resource-group <managed-resource-group> \
  --workspace-name <workspace-name>
```

Basic/public Bastion cannot be converted in place to Premium private-only
Bastion. Before enabling the Dev jumpbox on an existing environment, the
workflow fails closed if it finds the legacy Bastion, its public IP, or the
retired Windows jumpbox assets. Confirm there are no active Bastion sessions,
then explicitly remove `bastion-<base>`, `pip-bastion-<base>`,
`vm-jumpbox-<base>`, `nic-jumpbox-<base>`, and `nsg-jumpbox-<base>`. Rerun only
after cleanup; Azure permits one Bastion per VNet and `AzureBastionSubnet`, so
side-by-side Bastion migration is not supported.

ARC controller, listener, and runner pods are ephemeral managed workloads. They
must not be used for interactive troubleshooting, credential storage, or
long-lived administration. Use the Dev jumpbox or another approved private
administration path.

## Migration and rollback

Use this order for an existing AML Kubernetes endpoint:

1. Deploy the workspace managed-network settings and endpoint UAMI.
2. Provision the managed network and verify its private connections.
3. Create the distinctly named `managed-online-*` endpoint and deployment
   without changing callers. It can coexist with the legacy Kubernetes endpoint
   because the names and resource kinds are not reused.
4. Validate private DNS, identity access, quota, probes, logs, and direct
   deployment invocation.
5. Update callers to the managed endpoint scoring URI, validate Entra token
   acquisition, and observe the new path before retiring the old endpoint.
6. Delete the old Kubernetes online endpoint and deployments.
7. Detach the Kubernetes compute from the workspace.
8. Delete the `Microsoft.AzureML.Kubernetes` extension.
9. Delete extension TLS/CA secrets and extension-specific scoring DNS.
10. Remove inference-only node pools and namespaces only after confirming ARC is
    unaffected.

Before step 6, rollback consists of routing callers back to the previous endpoint.
After Kubernetes retirement starts, recreate only from the prior reviewed
infrastructure version; do not leave a partially attached extension/compute
state.

This repository does not deploy or remove Azure resources automatically as part
of migration. Run validation first, then use the environment-protected
infrastructure and online workflows deliberately.
