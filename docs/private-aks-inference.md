# Private Azure ML online inference on AKS

The generated Python SDK v2 project includes an opt-in Bicep pattern that adds
inference capacity to an existing private AKS cluster and attaches it directly to
Azure Machine Learning through AKS Trusted Access. The per-workspace
`Microsoft.MachineLearningServices/workspaces/mlworkload` binding is the supported
path for private clusters with local accounts disabled. The pattern keeps local
accounts disabled and does not weaken the workspace, storage, registry, cluster,
NAT, or private DNS controls.

## Support decision

As of 2026-09-16, Azure Machine Learning documents an AKS-aligned Kubernetes N-2
support window. AKS 1.36 is the latest GA minor and AKS 1.35 remains GA and in
standard support, so 1.35 is inside the documented Azure ML extension window
(1.34 through 1.36). The checked CLI versions were Azure CLI 2.90.0,
`k8s-extension` 1.8.0, and `ml` 2.44.1.

Do not pin the latest chart number found in documentation. Before each consumer
deployment, use the current `k8s-extension` CLI to query the stable
`Microsoft.AzureML.Kubernetes` versions for the AKS cluster and region. The query
can be unavailable until the `Microsoft.KubernetesConfiguration` provider and
extension-types API are exposed in the target subscription.

Authoritative references:

- https://learn.microsoft.com/azure/machine-learning/reference-kubernetes
- https://learn.microsoft.com/azure/aks/supported-kubernetes-versions
- https://learn.microsoft.com/azure/machine-learning/how-to-deploy-kubernetes-extension
- https://learn.microsoft.com/azure/machine-learning/how-to-attach-kubernetes-to-workspace
- https://learn.microsoft.com/azure/machine-learning/how-to-secure-kubernetes-online-endpoint

## What the Bicep deployment owns

When `enable_private_aks_inference: true`, the subscription deployment:

- adds an autoscaling `User` node pool to the existing AKS cluster;
- labels inference nodes `ml.azure.com/inference=true`;
- taints them `ml.azure.com/amlarc=true:NoSchedule`, which the Azure ML extension
  supports and ARC runner pods do not tolerate;
- configures the Azure ML extension node selector so extension and model pods do
  not consume the two-node system/ARC pool;
- creates a per-workspace AKS Trusted Access role binding before compute attach;
- installs `Microsoft.AzureML.Kubernetes` from the stable train with inference
  only, router HA, HTTPS, and an Azure internal load balancer;
- creates a dedicated inference UAMI and OIDC federated credential;
- grants the UAMI only `AcrPull` and `Storage Blob Data Reader`;
- grants the workspace UAMI the documented AKS attachment roles and Managed
  Identity Operator on the inference UAMI;
- registers the AKS managed-cluster resource as an AML `Kubernetes` compute and
  defines the configured instance type.

The workload identity federation is available to pods that carry the required
`azure.workload.identity/use: "true"` pod label. Azure ML does not document a
supported way to replace or arbitrarily annotate every generated online
deployment pod. The attached-compute UAMI remains the documented identity used by
Azure ML for ACR and Blob access; do not treat workload federation as a substitute
for AML compute or endpoint identity.

## Required configuration

Keep the feature disabled until all prerequisites exist. Then set:

```yaml
enable_private_aks_inference: true
aks_cluster_resource_id: "/subscriptions/<subscription>/resourceGroups/<aks-rg>/providers/Microsoft.ContainerService/managedClusters/<aks-name>"
aks_node_subnet_resource_id: "/subscriptions/<subscription>/resourceGroups/<network-rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<node-subnet>"
runner_hub_vnet_resource_id: "/subscriptions/<subscription>/resourceGroups/<network-rg>/providers/Microsoft.Network/virtualNetworks/<aks-runner-hub-vnet>"
online_compute: aks-inference
online_mlflow_no_code: true
online_environment_name: ""
online_environment_version: ""
online_environment_image: ""
online_instance_type: cpu-small
online_namespace: azureml-inference
online_service_account: default
online_node_pool_name: mlinference
online_node_vm_size: Standard_D4s_v3
online_node_min_count: 3
online_node_max_count: 6
online_node_max_pods: 30
online_cpu_request: 500m
online_cpu_limit: "2"
online_memory_request: 1Gi
online_memory_limit: 4Gi
aml_kubernetes_extension_name: azureml
aml_kubernetes_extension_release_train: stable
aml_kubernetes_extension_ssl_cname: <private-scoring-fqdn>
```

`online_instance_type` is an AML Kubernetes instance type, not an Azure VM SKU.
The reusable online workflow consumes `online_compute`,
`online_mlflow_no_code`, and `online_instance_type`. In the default MLflow no-code
mode, the generated caller passes `mlflow_no_code: true` and omits the environment
name and version inputs. Bicep also skips workspace environment creation.
Namespace, service account, UAMI, node pool, and AKS credentials remain
infrastructure-only.

For compatibility with an approved external image supply chain, set
`online_mlflow_no_code: false` and provide all three values together:

```yaml
online_environment_name: taxi-inference
online_environment_version: "1"
online_environment_image: "<registry>.azurecr.io/mlops/online-runtime@sha256:<64-hex-digest>"
```

The image-only path registers that exact workspace environment version. Partial
triples, mutable image references, and any environment input combined with
no-code mode fail validation.

## Consumer deployment prerequisites

Before enabling the feature:

1. Keep the AKS cluster private, managed-identity based, x86-64, and in the same
   region as the private-link AML workspace. OIDC issuer and Workload ID must be
   enabled. Keep AKS local accounts disabled. Set `aks_node_subnet_resource_id`
   to the existing Azure CNI Overlay node subnet; no separate pod subnet is used.
2. Register `Microsoft.KubernetesConfiguration`,
   `Microsoft.MachineLearningServices`, `Microsoft.ContainerService`, and
   `Microsoft.ManagedIdentity`. Confirm every provider reports `Registered`
   before deployment. Confirm
   `az aks trustedaccess role list --location <region>` includes
   `Microsoft.MachineLearningServices/workspaces/mlworkload`.
3. Configure the GitHub Environment secrets
   `AML_KUBERNETES_EXTENSION_TLS_CERT_PEM` and
   `AML_KUBERNETES_EXTENSION_TLS_KEY_PEM`. The workflow passes them directly as
   secure Bicep parameters; they are never written to config or committed. Bicep
   sends them to the extension through `configurationProtectedSettings`.
4. The deployment principal needs Contributor and Role Based Access Control
   Administrator at every resource scope it changes, including the existing AKS
   resource group and inference UAMI.
5. Ensure the runner-hub/AKS VNet has bidirectional routing and private DNS to the
   workload VNet and its AML, ACR, Storage, and Key Vault private endpoints. Keep
   workspace `publicNetworkAccess=Disabled`, storage
   `allowSharedKeyAccess=false`, and the existing NAT/private-cluster controls.
6. Allow controlled outbound DNS/HTTPS from inference nodes and pods to Microsoft
   Entra ID, Azure Resource Manager, Azure ML regional APIs, MCR, the private ACR
   data endpoint, private Storage endpoints, and required Azure telemetry hosts.
   NAT does not replace DNS or firewall allowlists.
7. The Bicep deployment applies the checked-in namespace/service-account
   manifest idempotently through AKS Run Command before extension installation,
   and extension completion is a dependency of AML compute attachment. The
   template creates a custom role containing only `runCommand/action` and
   `commandResults/read` and assigns it to the workspace UAMI at the AKS scope.
   The deployment principal needs permission to create that role and assignment.
   After deployment, read the internal load-balancer IP from
   `azureml-fe.status.loadBalancer.ingress[0].ip` and create a private DNS **A
   record** for `aml_kubernetes_extension_ssl_cname`. Do not create a CNAME that
   points at an IP address:

   ```bash
   aks_subscription="$(cut -d/ -f3 <<<"$AKS_CLUSTER_RESOURCE_ID")"
   aks_resource_group="$(cut -d/ -f5 <<<"$AKS_CLUSTER_RESOURCE_ID")"
   aks_name="$(cut -d/ -f9 <<<"$AKS_CLUSTER_RESOURCE_ID")"
   frontend_ip="$(az aks command invoke \
     --subscription "$aks_subscription" \
     --resource-group "$aks_resource_group" \
     --name "$aks_name" \
     --command "kubectl get service azureml-fe -n azureml -o jsonpath='{.status.loadBalancer.ingress[0].ip}'" \
     --query logs --output tsv)"
   test -n "$frontend_ip"
   az network private-dns record-set a add-record \
     --resource-group "$PRIVATE_DNS_RESOURCE_GROUP" \
     --zone-name "$PRIVATE_DNS_ZONE" \
     --record-set-name "$PRIVATE_DNS_RECORD_NAME" \
     --ipv4-address "$frontend_ip"
   ```

   For example, FQDN `scoring.internal.example`, zone `internal.example`, and
   record-set name `scoring` produce the required A record. The same FQDN is
   supplied as `sslCname`; it must match a DNS Subject Alternative Name in the
   server certificate. A matching legacy certificate Common Name alone is not
   sufficient. The deployment workflow rejects certificates with no DNS SAN or
   a hostname mismatch before sending the secure Bicep parameters.
8. Use the default `online_mlflow_no_code: true` for registered MLflow models.
   Azure ML supplies the curated serving environment, so the project does not
   create a workspace environment, publish a runtime image, or carry a custom
   online runtime Dockerfile. Non-root Kaniko runtime builds were tested and are
   conclusively unsupported by the enforced runner policy because the executor
   attempts `chown /` and fails with `operation not permitted`. Do not weaken
   the runner, mount a Docker socket, or introduce another in-cluster builder.
   If an organization already has an approved external image supply chain, use
   the immutable image-only compatibility configuration above. Bicep registers
   the supplied named/versioned environment with only the digest-pinned image;
   it has no build context or Conda file.
9. Run read-only preflight checks for AKS 1.35 patch support, extension stable
   versions, OIDC issuer, Workload ID, private DNS, node quota, and TLS material.
   Validate in nonproduction because Microsoft does not explicitly document the
   complete Kubernetes-online-endpoint combination with workspace storage shared
   keys disabled.

Microsoft Learn's generic extension limitations page still says local accounts
can't be disabled. The newer AKS Trusted Access documentation and the official
Azure/AML-Kubernetes guidance explicitly support AML access to private AKS with
local accounts disabled through the `mlworkload` binding:

- https://learn.microsoft.com/azure/aks/trusted-access-feature
- https://github.com/Azure/AML-Kubernetes/blob/master/docs/azureml-aks-ta-support.md
