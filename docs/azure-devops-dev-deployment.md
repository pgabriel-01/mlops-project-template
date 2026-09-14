# Deploy Classical AML CLI v2 to DEV

This runbook deploys the Classical Machine Learning AML CLI v2 pattern to a DEV
Azure environment with Azure DevOps and Terraform.

## Repository ownership

`pgabriel-01/mlops-project-template` owns:

- `config-infra-common.yml` and `config-infra-dev.yml`;
- the Terraform root and modules under `infrastructure/terraform`;
- workload code, data, and Azure ML definitions under `classical/aml-cli-v2`;
- the Terraform, training, online endpoint, and batch endpoint pipeline
  entrypoints.

`pgabriel-01/mlops-templates` owns composed, fail-fast Azure DevOps execution
templates under `templates/infra` and `templates/aml-cli-v2`. The project pipelines consume an
immutable commit from the `mlops_templates_ref` variable in
`config-infra-common.yml`. Update only that variable when promoting a validated
template release.

## Prerequisites

- An Azure subscription and tenant with quota for the selected AML compute and
  endpoint SKUs.
- An Azure DevOps project with this repository and `mlops-templates` available
  as Git repositories.
- Microsoft-hosted agent capacity, or an authorized self-hosted pool.
- The Terraform Azure DevOps extension used by the reusable install step.
- An Azure Resource Manager service connection named `Azure-ARM-Dev` using
  workload identity federation.
- Pipeline authorization to read `mlops-templates` and use `Azure-ARM-Dev`.
- Build Service read permission on both repositories.
- The service connection principal must be able to create the configured
  resources and role assignments. Contributor alone cannot create role
  assignments; grant an appropriate role such as User Access Administrator at
  the deployment scope when Terraform manages RBAC.

Set `cicd_principal_object_id` as a non-secret pipeline variable to the object ID
of the workload identity service principal. Terraform grants that principal AML
workspace Contributor and storage blob data access for training and deployment.

An Azure DevOps environment named `dev` is optional unless deployment jobs,
approvals, or checks are added.

## DEV configuration

Shared defaults are in `config-infra-common.yml`; DEV-specific location,
postfix, environment, and service connections are in `config-infra-dev.yml`.

Review these values before deployment:

- `namespace`, `project_number`, `postfix`, `location`, and `environment`;
- Terraform backend resource group, storage account, container, and state key;
- `aml_compute_sku`, training compute, batch compute, model, environment, data,
  endpoint, and deployment names;
- monitoring and AML compute flags;
- `cicd_principal_object_id`;
- `mlops_templates_ref`.

DEV defaults to `enable_private_endpoints: false`. Before enabling private
endpoints, provide private DNS resolution and an Azure DevOps agent with network
access to the AML workspace, storage account, Key Vault, and container registry.
Also review the VNet and subnet CIDRs for overlap.

## Pipeline entrypoints

Create these Azure DevOps pipelines:

| Purpose | YAML path |
| --- | --- |
| Terraform infrastructure | `infrastructure/terraform/devops-pipelines/tf-ado-deploy-infra.yml` |
| Train and register model | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-model-training-pipeline.yml` |
| Deploy online endpoint | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-online-endpoint-pipeline.yml` |
| Deploy batch endpoint | `classical/aml-cli-v2/mlops/devops-pipelines/deploy-batch-endpoint-pipeline.yml` |

All four pipelines are manual (`trigger: none`) and explicitly load DEV
configuration. Production branch routing is intentionally outside this rollout.

## Deployment sequence

1. Authorize both repositories and `Azure-ARM-Dev` for all four pipelines.
2. Run the Terraform infrastructure pipeline.
   - It creates the Azure AD-authenticated backend.
   - It disables backend storage shared-key access after creating the container.
   - It runs format check, init, validate, plan, and apply.
   - Confirm the resource group, AML workspace, storage account, container
     registry, workspace identity, and training compute outputs.
3. Run the training pipeline.
   - Terraform owns `cpu-cluster` when `enable_aml_computecluster` is true.
   - The pipeline registers the environment and data asset, submits the Azure ML
     pipeline, waits for completion, and registers `taxi-model`.
4. Run the online endpoint pipeline, the batch endpoint pipeline, or both.
   Endpoint deployment requires the registered model from step 3.
5. Re-run Terraform plan and the selected AML pipelines to confirm idempotency.

The batch endpoint pipeline owns its endpoint-specific batch compute. Reusable
templates fail the Azure DevOps job when setup, training, deployment, polling,
or scoring fails.

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
commit to verify repository-resource authorization, template paths, and
parameters.

For live DEV validation, confirm:

- the second Terraform plan has no unintended changes;
- workspace connection and Azure ML asset registration succeed;
- training completes and the configured model is registered;
- online scoring returns a response and/or batch scoring reaches `Completed`;
- repeated deployment updates or reuses resources without duplicate-name
  failures;
- a failed AML job or scoring invocation fails the Azure DevOps pipeline.

## Operations

Terraform state is environment-specific. Do not delete or recreate the backend
storage account during normal recovery. Correct the failing configuration and
re-run the pipeline.

AML asset and endpoint commands are expected to be idempotent create-or-update
operations. If an endpoint must be removed, delete it explicitly with the AML
CLI only after confirming it is no longer serving traffic. Infrastructure
destruction is not part of the deployment pipelines.
