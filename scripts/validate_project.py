from __future__ import annotations

import argparse
import re
from pathlib import Path

from project_config import load_config


ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
CONFIG_ROOT = PATTERN_ROOT
WORKFLOW_ROOT = PATTERN_ROOT / "mlops" / "github-actions"
ENVIRONMENTS = ("dev", "test", "prod")
REQUIRED_CONFIG = {
    "environment",
    "location",
    "namespace",
    "postfix",
    "project_number",
    "private_network",
    "runner",
    "runner_hub_vnet_resource_id",
    "manage_runner_hub_to_workload_peering",
    "python_version",
    "aml_compute_sku",
    "batch_compute_name",
    "model_name",
    "online_endpoint_suffix",
    "online_deployment_name",
    "online_instance_type",
    "batch_endpoint_suffix",
    "batch_deployment_name",
}
FORBIDDEN_PATH_PARTS = {
    "aml-cli-v2",
    "cv",
    "devops-pipelines",
    "nlp",
    "terraform",
    "python-sdk-v1",
    "rai-aml-cli-v2",
}
FORBIDDEN_CONTENT = (
    "AZURE_CREDENTIALS",
    "service connection",
    "variable group",
    "Managed DevOps Pool",
    "retail-demand-forecasting-mlops",
)
PLACEHOLDERS = {
    "__MLOPS_TEMPLATES_REPOSITORY__",
    "__MLOPS_TEMPLATES_REF__",
}


def generated_paths() -> list[Path]:
    bicep_modules = (
        "ai_foundry_hub.bicep",
        "ai_foundry_project.bicep",
        "aml_computecluster.bicep",
        "aml_registry.bicep",
        "aml_workspace.bicep",
        "apim.bicep",
        "application_insights.bicep",
        "bastion.bicep",
        "cmk.bicep",
        "container_registry.bicep",
        "defender.bicep",
        "key_vault.bicep",
        "managed_identity.bicep",
        "private_dns_zones.bicep",
        "private_endpoint.bicep",
        "rbac_persona_data_scientist.bicep",
        "rbac_persona_ml_engineer.bicep",
        "rbac_persona_team_lead.bicep",
        "storage_account.bicep",
        "vnet.bicep",
        "vnet_peering.bicep",
    )
    paths = [
        PATTERN_ROOT / "README.md",
        PATTERN_ROOT / "mlops" / "azureml" / "train" / "job.yml",
        *[CONFIG_ROOT / f"config-infra-{environment}.yml" for environment in ENVIRONMENTS],
        *WORKFLOW_ROOT.glob("*.yml"),
        ROOT / "scripts" / "export_config.py",
        ROOT / "scripts" / "project_config.py",
        ROOT / "scripts" / "render_bicep_parameters.py",
        ROOT / "scripts" / "validate_project.py",
        ROOT / "infrastructure" / "bicep" / "bicepconfig.json",
        ROOT / "infrastructure" / "bicep" / "main.bicep",
        *[
            ROOT / "infrastructure" / "bicep" / "modules" / module
            for module in bicep_modules
        ],
    ]
    return sorted(paths)


def validate_tree() -> list[str]:
    errors: list[str] = []
    for path in generated_paths():
        relative = path.relative_to(ROOT)
        if not path.is_file():
            errors.append(f"missing generated path: {relative}")
            continue
        if FORBIDDEN_PATH_PARTS.intersection(relative.parts):
            errors.append(f"forbidden generated path: {relative}")
    return errors


def validate_config_values(path: Path, config: dict[str, object]) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_CONFIG - config.keys()
    if missing:
        errors.append(f"{path.name} missing: {', '.join(sorted(missing))}")
    environment = path.stem.removeprefix("config-infra-")
    if config.get("environment") != environment:
        errors.append(f"{path.name} has wrong environment")
    if config.get("private_network") and config.get("runner") in {
        "ubuntu-latest",
        "ubuntu-24.04",
    }:
        errors.append(f"{path.name} private network requires a private runner")
    runner_hub_vnet_resource_id = config.get("runner_hub_vnet_resource_id", "")
    if runner_hub_vnet_resource_id and not re.fullmatch(
        r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
        r"Microsoft\.Network/virtualNetworks/[^/]+",
        str(runner_hub_vnet_resource_id),
        re.IGNORECASE,
    ):
        errors.append(f"{path.name} has an invalid runner hub VNet resource ID")
    if config.get("manage_runner_hub_to_workload_peering") and not (
        runner_hub_vnet_resource_id
    ):
        errors.append(
            f"{path.name} cannot manage reciprocal peering without a runner hub"
        )
    if runner_hub_vnet_resource_id and not config.get("enable_vnet"):
        errors.append(
            f"{path.name} cannot integrate a runner hub when VNet is disabled"
        )
    return errors


def validate_configs() -> list[str]:
    errors: list[str] = []
    for environment in ENVIRONMENTS:
        path = CONFIG_ROOT / f"config-infra-{environment}.yml"
        config = load_config(path)
        errors.extend(validate_config_values(path, config))
    return errors


def validate_workflows(require_resolved_templates: bool) -> list[str]:
    errors: list[str] = []
    workflow_dir = WORKFLOW_ROOT
    deployment_workflows = (
        "deploy-infrastructure.yml",
        "train-register-model.yml",
        "deploy-online-endpoint.yml",
        "deploy-batch-endpoint.yml",
    )
    for name in deployment_workflows:
        path = workflow_dir / name
        if not path.exists():
            errors.append(f"missing workflow: {name}")
            continue
        content = path.read_text(encoding="utf-8")
        if "environment:" not in content:
            errors.append(f"{name} does not pass a GitHub Environment")
        if "AZURE_CREDENTIALS" in content:
            errors.append(f"{name} uses client-secret credentials")
        if "id-token: write" not in content:
            errors.append(f"{name} does not request OIDC")
        if (
            "config-infra-${{ inputs.environment }}.yml" not in content
            and "config-infra-${{ needs.config.outputs.environment }}.yml"
            not in content
        ):
            errors.append(f"{name} does not select an environment config")
        if require_resolved_templates and PLACEHOLDERS.intersection(
            re.findall(r"__[A-Z0-9_]+__", content)
        ):
            errors.append(f"{name} contains unresolved template placeholders")
        for reference in re.findall(r"uses:\s+([^\s]+)", content):
            ref = reference.rsplit("@", 1)[-1]
            if "__MLOPS_TEMPLATES_REF__" != ref and not re.fullmatch(
                r"[0-9a-f]{40}", ref
            ):
                errors.append(f"{name} has mutable action reference: {reference}")
    return errors


def validate_content() -> list[str]:
    errors: list[str] = []
    for path in generated_paths():
        if path == PATTERN_ROOT / "README.md" or path.parent == ROOT / "scripts":
            continue
        if not path.is_file() or path.suffix not in {
            ".bicep",
            ".json",
            ".md",
            ".py",
            ".yml",
            ".yaml",
        }:
            continue
        content = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_CONTENT:
            if forbidden.lower() in content.lower():
                errors.append(f"{path.relative_to(ROOT)} contains {forbidden!r}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-resolved-templates", action="store_true")
    args = parser.parse_args()

    errors = [
        *validate_tree(),
        *validate_configs(),
        *validate_workflows(args.require_resolved_templates),
        *validate_content(),
    ]
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
