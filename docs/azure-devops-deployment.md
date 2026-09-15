# Deploy Classical AML CLI v2 with Azure DevOps

This runbook deploys the Classical Machine Learning AML CLI v2 pattern to DEV,
Test, or Prod Azure environments with Azure DevOps and Terraform. It supports
Microsoft-hosted agents for public DEV resources and Managed DevOps Pool agents
for private/keyless environments.

## Repository ownership

`pgabriel-01/mlops-project-template` owns:

- `config-infra-common.yml` and `config-infra-dev.yml`;
- the Terraform root and modules under `infrastructure/terraform`;
- workload code, data, and Azure ML definitions under `classical/aml-cli-v2`;
- the Terraform, training, online endpoint, and batch endpoint pipeline
  entrypoints.

`pgabriel-01/mlops-templates` owns composed, fail-fast Azure DevOps execution
templates for platform bootstrap, Terraform, and AML CLI v2. Pipeline parameter
`mlopsTemplatesRef` defaults to `refs/heads/main`; before
`pgabriel-01/mlops-templates#1` is merged, queue pipelines with its documented
immutable commit SHA,
`1d7ac905094799455fc7112add7d1d8209b0ca77`. Release tags or commit SHAs are
recommended for controlled promotion.

## Prerequisites

- An Azure subscription and tenant with quota for the selected AML compute and
  endpoint SKUs.
- An Azure DevOps project with this repository and `mlops-templates` available
  as Git repositories.
- Microsoft-hosted agent capacity, or an authorized self-hosted pool.
- The Terraform Azure DevOps extension used by the reusable install step.
- Azure Resource Manager service connections using workload identity federation.
- Pipeline authorization to read `mlops-templates` and use the selected
  environment's service connections.
- Build Service read permission on both repositories.
- The service connection principal must be able to create the configured
  resources and role assignments. Contributor alone cannot create role
  assignments; grant an appropriate role such as User Access Administrator at
  the deployment scope when Terraform manages RBAC.

Create Azure DevOps variable groups named `mlops-dev`, `mlops-test`, and
`mlops-prod`. Each group must define:

- `ado_service_connection_rg`;
- `ado_service_connection_aml_ws`;
- `cicd_principal_object_id`, the Entra object ID of the workload identity
  service principal;
- `devops_infrastructure_principal_object_id`, the Entra object ID of the
  Microsoft DevOpsInfrastructure service principal in the tenant;
- `devcenter_project_resource_id`, the full Azure resource ID of the Dev Center
  project used by the Managed DevOps Pool.

Do not commit live service connection names, tenant/subscription IDs, principal
IDs, organization URLs, project IDs, or credentials. Platform bootstrap values
are supplied through the same protected environment variable groups.

Azure DevOps environments named `dev`, `test`, and `prod` are optional unless
deployment jobs, approvals, or checks are added.

The upstream factory may generate a deployment manifest with these keys:

- `network_mode`;
- `deployment_environment`;
- `variable_group_name`;
- `mlops_templates_ref`;
- `platform_service_connection_name`;
- `workload_service_connection_name`;
- `managed_devops_pool_name`;
- `managed_devops_pool_alias`;
- `managed_devops_pool_resource_group`;
- `managed_devops_pool_location`;
- `managed_devops_pool_vm_sku`.

The repository environment files and queue-time pipeline parameters expose the
matching values without embedding live Azure DevOps identifiers.

## Environment configuration

Shared defaults are in `config-infra-common.yml`. Environment-specific values
are in:

- `config-infra-dev.yml`;
- `config-infra-test.yml`;
- `config-infra-prod.yml`.

Review these values before deployment:

- `namespace`, `project_number`, `postfix`, `location`, and `environment`;
- Terraform backend resource group, storage account, container, and state key;
- `aml_compute_sku`, training compute, model, environment, data,
  endpoint, and deployment names;
- monitoring and AML compute flags;
- the matching variable group;
- the `mlopsTemplatesRef` queue-time parameter;
- the `agentPoolName` queue-time parameter.

`terraform_version` is set to `1.16.x`. The reusable resolver selects the latest
stable patch in the Terraform 1.16 release line before invoking
`TerraformInstaller@1`.

DEV defaults to public endpoints and Microsoft-hosted agents. Test and Prod
default to private endpoints and the environment's
`managed_devops_pool_alias`. `agentPoolName` overrides that default when a
different authorized pool is required. Review VNet/subnet CIDRs for overlap
before platform bootstrap. Private environments use separate platform and
workload VNets: Terraform peers them, links workload private DNS zones to the
platform VNet, and reuses the platform Blob private DNS zone for both state and
workload storage. Terraform enables the AML managed VNet in
`AllowInternetOutbound` mode through an in-place Azure API workspace update,
avoiding workspace replacement and soft-delete name retention. AML-managed
network provisioning runs only after the workspace private endpoint completes.
Both workspace identities receive `Azure AI Enterprise Network Connection
Approver` directly on the workspace Storage Account, Key Vault, and Container
Registry. They also receive Container Registry `Reader`, which supplies the
registry metadata permission omitted by the approver and `AcrPush` roles.
Terraform uses a target-scope/contract-sensitive 120-second propagation barrier
before provisioning the managed network. AML-managed compute then waits for the
private endpoint and managed-network provisioning, uses the managed network with
node public IPs disabled, and is not attached to the user-managed training
subnet. Existing computes must still be deleted and recreated when migrating
them to AML managed networking. Private online deployment definitions omit
`egress_public_network_access`, which Azure ML no longer accepts when the
workspace uses a managed VNet.

## Pipeline entrypoints

Create these Azure DevOps pipelines:

| Purpose | YAML path |
| --- | --- |
| Platform network, private pool, and state backend | `infrastructure/terraform/devops-pipelines/platform-ado-bootstrap.yml` |
| Terraform infrastructure | `infrastructure/terraform/devops-pipelines/tf-ado-deploy-infra.yml` |
| Train and register model | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-model-training-pipeline.yml` |
| Deploy online endpoint | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-online-endpoint-pipeline.yml` |
| Deploy batch endpoint | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-batch-endpoint-pipeline.yml` |

All pipelines are manual (`trigger: none`). At queue time select:

- `environment`: `dev`, `test`, or `prod`;
- `agentPoolName`: optional override; empty uses Microsoft-hosted agents for
  public DEV and `managed_devops_pool_name` for private environments;
- `mlopsTemplatesRef`: `refs/heads/main` by default, or a release tag/commit.

## Deployment sequence

1. Authorize both repositories and the selected variable-group service
   connections for all pipelines.
2. Run the platform bootstrap pipeline from a Microsoft-hosted agent. It creates
   or updates the keyless Terraform state backend and Managed DevOps Pool for
   every environment. In private mode it also creates the platform VNet, pool
   subnet, Blob private endpoint, and DNS prerequisites. The state backend shares
   `managed_devops_pool_resource_group`.
3. Run the Terraform infrastructure pipeline on the selected private pool (or a
   Microsoft-hosted agent for public DEV).
   - It creates the Azure AD-authenticated backend.
   - It runs format check, init, validate, plan, and apply.
   - Confirm the resource group, AML workspace, storage account, container
     registry, workspace identity, and training compute outputs.
4. Run the training pipeline with the same environment, pool, and template ref.
   - Terraform owns `cpu-cluster` when `enable_aml_computecluster` is true.
   - The pipeline registers the environment and data asset, submits the Azure ML
     pipeline, waits for completion, and registers `taxi-model`.
5. Run the online endpoint pipeline, the batch endpoint pipeline, or both.
   Endpoint deployment requires the registered model from step 4.
6. Re-run Terraform plan and the selected AML pipelines to confirm idempotency.

Online deployment uses `Standard_D2ds_v5`; private environments select a
deployment definition with public egress disabled. Batch deployment reuses the
Terraform-managed `cpu-cluster`, preserving its managed-network and
no-public-IP configuration instead of creating a separate pipeline-owned
compute cluster.
Reusable templates fail the Azure DevOps job when setup, training, deployment,
polling, or scoring fails.

## Validation

Before a live deployment:

```bash
terraform fmt -check -recursive infrastructure/terraform
terraform -chdir=infrastructure/terraform init -backend=false
terraform -chdir=infrastructure/terraform validate
python3 -m compileall classical/aml-cli-v2/data-science/src \
  classical/aml-cli-v2/mlops/azureml/deploy
```

Compile or preview each Azure DevOps YAML pipeline against the pinned template
commit `1d7ac905094799455fc7112add7d1d8209b0ca77` to verify
repository-resource authorization, template paths, and parameters.

Run the project contract tests:

```bash
python3 -m unittest tests/test_ado_deployment_wiring.py
```

For live environment validation, confirm:

- the second Terraform plan has no unintended changes;
- the platform and workload VNet peerings are connected, and the private pool
  resolves the AML, registry, vault, and storage private endpoint names;
- workspace connection and Azure ML asset registration succeed;
- training completes and the configured model is registered;
- online scoring returns a response and/or batch scoring reaches `Completed`;
- repeated deployment updates or reuses resources without duplicate-name
  failures;
- a failed AML job or scoring invocation fails the Azure DevOps pipeline.

## Operations

Terraform state keys and backends are environment-specific and use Azure AD
authentication with shared-key access disabled. Do not delete or recreate the
backend storage account during normal recovery. Correct the failing
configuration and re-run the pipeline.

AML asset and endpoint commands are expected to be idempotent create-or-update
operations. If an endpoint must be removed, delete it explicitly with the AML
CLI only after confirming it is no longer serving traffic. Infrastructure
destruction is not part of the deployment pipelines.
