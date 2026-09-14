# Azure MLOps v2 project template

This repository contains project-owned infrastructure and workload assets derived
from the [Azure MLOps v2](https://github.com/Azure/mlops-v2) patterns. Reusable
Azure DevOps execution templates are maintained separately in
[`pgabriel-01/mlops-templates`](https://github.com/pgabriel-01/mlops-templates).

The supported DEV deployment path uses:

- Terraform for Azure Machine Learning infrastructure;
- Azure DevOps with workload identity federation;
- the Classical Machine Learning AML CLI v2 workload;
- pinned reusable pipeline templates.

See [Deploy Classical AML CLI v2 to DEV](docs/azure-devops-dev-deployment.md)
for prerequisites, configuration, pipeline entrypoints, deployment order, and
validation.
