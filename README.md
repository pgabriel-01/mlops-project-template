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
provide these secrets:

| Secret | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID of the environment's federated workload identity |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription |

Configure the federated identity subject for each environment as
`repo:<owner>/<repository>:environment:<environment>`. No client secret is used.

Environment settings live in `config-infra-dev.yml`, `config-infra-test.yml`, and
`config-infra-prod.yml`. The default private-network configuration uses the
`mlops-private` runner label; register an approved self-hosted runner with that
label and network/DNS access to the private endpoints, or replace it with a label
approved by your organization. Do not switch a private deployment to a
GitHub-hosted runner unless it has an explicit network path to the resources.

Each GitHub Environment must also define `AZURE_PRINCIPAL_OBJECT_ID` as a variable.
It is the object ID of the federated CI principal and is used only for idempotent
role assignments in Bicep.

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

## Keyless private architecture

Bicep disables storage shared-key access, configures identity-authenticated system
datastores, and grants the workspace identity data-plane access. When private
networking is enabled, the deployment includes managed network isolation plus
private endpoints and DNS zones for the workspace, registry, vault, and storage
blob, file, queue, and table services.

This repository does not apply network changes automatically outside the explicit
infrastructure workflow.

## Local validation

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python scripts/validate_project.py
az bicep build --file infrastructure/bicep/main.bicep
```
