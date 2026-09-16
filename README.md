# Azure MLOps v2 project template

This repository contains project-owned infrastructure and workload assets derived
from the [Azure MLOps v2](https://github.com/Azure/mlops-v2) patterns. Reusable
Azure DevOps execution templates are maintained separately in
[`pgabriel-01/mlops-templates`](https://github.com/pgabriel-01/mlops-templates).

The supported Azure DevOps deployment path uses:

- Terraform for Azure Machine Learning infrastructure;
- Azure DevOps with workload identity federation;
- the Classical Machine Learning AML CLI v2 workload;
- reusable pipeline templates from `mlops-templates`;
- public DEV or private/keyless DEV, Test, and Prod environments;
- a platform bootstrap for keyless state and Managed DevOps Pools.

See [Deploy Classical AML CLI v2 with Azure DevOps](docs/azure-devops-deployment.md)
for prerequisites, configuration, pipeline entrypoints, deployment order, and
validation.

For the generated Python SDK v2/GitHub Actions project, see
[Private Azure ML online inference on AKS](docs/private-aks-inference.md) for the
opt-in, fully private Kubernetes serving infrastructure contract.
