from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from project_config import load_config


SCRIPT_ROOT = Path(__file__).resolve().parent
if SCRIPT_ROOT.parent.parent.name == "python-sdk-v2":
    ROOT = SCRIPT_ROOT.parents[3]
    PATTERN_ROOT = SCRIPT_ROOT.parent.parent
    INFRASTRUCTURE_ROOT = ROOT / "infrastructure" / "bicep"
    CONFIG_ROOT = PATTERN_ROOT
    WORKFLOW_ROOT = PATTERN_ROOT / "mlops" / "github-actions"
else:
    ROOT = SCRIPT_ROOT.parents[1]
    PATTERN_ROOT = ROOT
    INFRASTRUCTURE_ROOT = ROOT / "infrastructure"
    CONFIG_ROOT = ROOT
    WORKFLOW_ROOT = ROOT / ".github" / "workflows"
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
    "shared_private_dns_zone_resource_ids",
    "enable_managed_online_endpoint",
    "python_version",
    "aml_compute_sku",
    "batch_compute_name",
    "model_name",
    "online_endpoint_suffix",
    "online_deployment_name",
    "online_alternate_deployment_name",
    "online_traffic_percentage",
    "online_lock_container_name",
    "online_instance_type",
    "online_instance_count",
    "online_mlflow_no_code",
    "online_environment_name",
    "online_environment_version",
    "online_environment_image",
    "online_code_directory",
    "online_scoring_script",
    "online_endpoint_allow_key_vault_secrets",
    "batch_endpoint_suffix",
    "batch_deployment_name",
    "enable_dev_jumpbox",
    "bastion_subnet_prefix",
    "administration_subnet_prefix",
    "dev_jumpbox_vm_size",
    "dev_jumpbox_ubuntu_image_version",
    "dev_jumpbox_azure_cli_version",
    "dev_jumpbox_azure_ml_extension_version",
    "dev_jumpbox_azure_ai_ml_version",
    "dev_jumpbox_azure_identity_version",
    "dev_jumpbox_shutdown_time",
    "dev_jumpbox_shutdown_timezone",
    "dev_jumpbox_login_group_id",
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
    "AZURE_" + "CREDENTIALS",
    "service connection",
    "variable group",
    "Managed DevOps Pool",
    "retail-demand-forecasting-mlops",
)
PLACEHOLDERS = {
    "__MLOPS_TEMPLATES_REPOSITORY__",
    "__MLOPS_TEMPLATES_REF__",
}
PRIVATE_DNS_ZONE_NAMES = {
    "privatelink.blob.core.windows.net",
    "privatelink.file.core.windows.net",
    "privatelink.queue.core.windows.net",
    "privatelink.table.core.windows.net",
    "privatelink.dfs.core.windows.net",
    "privatelink.vaultcore.azure.net",
    "privatelink.azurecr.io",
    "privatelink.api.azureml.ms",
    "privatelink.notebooks.azure.net",
}
VERIFIED_JUMPBOX_IMAGES = {
    ("eastus", "24.04.202608270"),
    ("eastus2", "24.04.202608270"),
}


def generated_paths() -> list[Path]:
    bicep_modules = (
        "ai_foundry_hub.bicep",
        "ai_foundry_project.bicep",
        "aml_computecluster.bicep",
        "aml_online_endpoint_identity.bicep",
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
        "private_dns_zone_vnet_link.bicep",
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
        PATTERN_ROOT / "data-science" / "environment" / "train-conda.yml",
        PATTERN_ROOT / "data-science" / "src" / "evaluate" / "evaluate.py",
        PATTERN_ROOT / "data-science" / "src" / "prep" / "prep.py",
        PATTERN_ROOT / "data-science" / "src" / "register" / "register.py",
        PATTERN_ROOT / "data-science" / "src" / "train" / "train.py",
        PATTERN_ROOT / "data" / "taxi-batch.csv",
        PATTERN_ROOT / "data" / "taxi-data.csv",
        PATTERN_ROOT / "data" / "taxi-request.json",
        PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "batch" / "score.py",
        PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "deploy.py",
        PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "deployment_lock.py",
        PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "requirements.txt",
        PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "code" / "score.py",
        PATTERN_ROOT / "mlops" / "scripts" / "check_legacy_bastion.py",
        PATTERN_ROOT / "mlops" / "azureml" / "train" / "job.yml",
        *[
            CONFIG_ROOT / f"config-infra-{environment}.yml"
            for environment in ENVIRONMENTS
        ],
        *WORKFLOW_ROOT.glob("*.yml"),
        SCRIPT_ROOT / "export_config.py",
        PATTERN_ROOT / "runner-bootstrap" / "manifests" / "arc-operator-rbac.json",
        PATTERN_ROOT / "runner-bootstrap" / "scripts" / "install_arc.sh",
        PATTERN_ROOT / "runner-bootstrap" / "scripts" / "invoke_aks_command.py",
        SCRIPT_ROOT / "project_config.py",
        SCRIPT_ROOT / "render_bicep_parameters.py",
        SCRIPT_ROOT / "validate_project.py",
        INFRASTRUCTURE_ROOT / "bicepconfig.json",
        INFRASTRUCTURE_ROOT / "assets" / "dev-jumpbox-bootstrap.pub",
        INFRASTRUCTURE_ROOT / "main.bicep",
        *[INFRASTRUCTURE_ROOT / "modules" / module for module in bicep_modules],
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
    if (
        config.get("private_network")
        and not str(config.get("batch_compute_name", "")).strip()
    ):
        errors.append(
            f"{path.name} private network requires batch_compute_name for "
            "workspace image builds"
        )
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
    try:
        shared_zone_ids = json.loads(
            str(config.get("shared_private_dns_zone_resource_ids", "{}"))
        )
    except json.JSONDecodeError:
        shared_zone_ids = None
        errors.append(f"{path.name} shared private DNS zone IDs must be a JSON object")
    if shared_zone_ids is not None and not isinstance(shared_zone_ids, dict):
        errors.append(f"{path.name} shared private DNS zone IDs must be a JSON object")
    if isinstance(shared_zone_ids, dict):
        if shared_zone_ids and not runner_hub_vnet_resource_id:
            errors.append(
                f"{path.name} cannot reuse runner hub DNS zones without a runner hub"
            )
        if shared_zone_ids and not config.get("enable_vnet"):
            errors.append(
                f"{path.name} cannot reuse private DNS zones when VNet is disabled"
            )
        for zone_name, zone_id in shared_zone_ids.items():
            expected_suffix = (
                f"/providers/Microsoft.Network/privateDnsZones/{zone_name}"
            )
            if (
                zone_name not in PRIVATE_DNS_ZONE_NAMES
                or not isinstance(zone_id, str)
                or not zone_id.lower().endswith(expected_suffix.lower())
                or not re.match(
                    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/",
                    zone_id,
                    re.IGNORECASE,
                )
            ):
                errors.append(
                    f"{path.name} has an invalid shared private DNS zone mapping "
                    f"for {zone_name}"
                )
    if config.get("enable_managed_online_endpoint"):
        if not config.get("private_network"):
            errors.append(
                f"{path.name} managed online endpoint requires private_network"
            )
        if not config.get("enable_vnet"):
            errors.append(f"{path.name} managed online endpoint requires enable_vnet")
        if not config.get("enable_container_registry"):
            errors.append(
                f"{path.name} managed online endpoint requires container registry"
            )
        if not re.fullmatch(
            r"Standard_[A-Za-z0-9_]+",
            str(config.get("online_instance_type", "")),
        ):
            errors.append(f"{path.name} online_instance_type must be an Azure VM SKU")
        if int(config.get("online_instance_count", 0)) < 1:
            errors.append(f"{path.name} online_instance_count must be at least one")
        if (
            environment in {"test", "prod"}
            and int(config.get("online_instance_count", 0)) < 3
        ):
            errors.append(
                f"{path.name} requires at least three managed endpoint instances"
            )
        if str(config.get("online_endpoint_suffix", "")).strip() == "online":
            errors.append(
                f"{path.name} managed endpoint suffix must not reuse the legacy "
                "Kubernetes endpoint name"
            )
        deployment_names = (
            str(config.get("online_deployment_name", "")),
            str(config.get("online_alternate_deployment_name", "")),
        )
        if deployment_names[0] == deployment_names[1]:
            errors.append(f"{path.name} blue-green deployment names must differ")
        for deployment_name in deployment_names:
            if not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?",
                deployment_name,
            ):
                errors.append(f"{path.name} has an invalid managed deployment name")
        if not 1 <= int(config.get("online_traffic_percentage", 0)) <= 100:
            errors.append(
                f"{path.name} online_traffic_percentage must be between 1 and 100"
            )
        if not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?",
            str(config.get("online_lock_container_name", "")),
        ):
            errors.append(f"{path.name} has an invalid deployment lock container name")
    mlflow_no_code = config.get("online_mlflow_no_code")
    if not isinstance(mlflow_no_code, bool):
        errors.append(f"{path.name} online_mlflow_no_code must be true or false")
        mlflow_no_code = False
    environment_name = str(config.get("online_environment_name", "")).strip()
    environment_version = str(config.get("online_environment_version", "")).strip()
    environment_image = str(config.get("online_environment_image", "")).strip()
    code_directory = str(config.get("online_code_directory", "")).strip()
    scoring_script = str(config.get("online_scoring_script", "")).strip()
    environment_values = (
        environment_name,
        environment_version,
        environment_image,
    )
    if mlflow_no_code and any(environment_values):
        errors.append(
            f"{path.name} MLflow no-code mode cannot define online environment "
            "name, version, or image"
        )
    if not mlflow_no_code and any(environment_values) and not all(environment_values):
        errors.append(
            f"{path.name} image-only mode requires online environment name, "
            "version, and image together"
        )
    if (
        config.get("enable_managed_online_endpoint")
        and not mlflow_no_code
        and not all(environment_values)
    ):
        errors.append(
            f"{path.name} image-only managed inference requires online "
            "environment name, version, and image"
        )
    if not mlflow_no_code and (not code_directory or not scoring_script):
        errors.append(
            f"{path.name} image-only managed inference requires a code "
            "directory and scoring script"
        )
    if code_directory and scoring_script:
        scoring_path = PATTERN_ROOT / code_directory / scoring_script
        if not scoring_path.is_file():
            errors.append(
                f"{path.name} online scoring script does not exist: {scoring_path}"
            )
    if environment_image and not re.fullmatch(
        r"[a-z0-9]+\.azurecr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
        environment_image,
    ):
        errors.append(
            f"{path.name} online environment image must use an immutable sha256 digest"
        )
    enable_dev_jumpbox = config.get("enable_dev_jumpbox")
    if not isinstance(enable_dev_jumpbox, bool):
        errors.append(f"{path.name} enable_dev_jumpbox must be true or false")
    if environment == "dev" and enable_dev_jumpbox is not True:
        errors.append(f"{path.name} must enable the Dev jumpbox by default")
    if environment != "dev" and enable_dev_jumpbox is not False:
        errors.append(f"{path.name} must disable the Dev jumpbox by default")
    if enable_dev_jumpbox and not config.get("enable_vnet"):
        errors.append(f"{path.name} Dev jumpbox requires enable_vnet")
    if str(config.get("dev_jumpbox_ubuntu_image_version", "")).lower() in {
        "",
        "latest",
    }:
        errors.append(f"{path.name} Dev jumpbox image version must be pinned")
    image_key = (
        str(config.get("location", "")).lower(),
        str(config.get("dev_jumpbox_ubuntu_image_version", "")),
    )
    if image_key not in VERIFIED_JUMPBOX_IMAGES:
        errors.append(
            f"{path.name} Dev jumpbox image is not verified for its target region"
        )
    for key in (
        "dev_jumpbox_azure_cli_version",
        "dev_jumpbox_azure_ml_extension_version",
        "dev_jumpbox_azure_ai_ml_version",
        "dev_jumpbox_azure_identity_version",
    ):
        if not str(config.get(key, "")).strip():
            errors.append(f"{path.name} {key} must be pinned")
    if not re.fullmatch(
        r"\d+\.\d+\.\d+",
        str(config.get("dev_jumpbox_azure_ml_extension_version", "")),
    ):
        errors.append(
            f"{path.name} Dev jumpbox Azure ML extension version must be pinned"
        )
    if not re.fullmatch(
        r"(?:[01][0-9]|2[0-3])[0-5][0-9]",
        str(config.get("dev_jumpbox_shutdown_time", "")),
    ):
        errors.append(f"{path.name} has an invalid Dev jumpbox shutdown time")
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
        if "AZURE_" + "CREDENTIALS" in content:
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
        if path == PATTERN_ROOT / "README.md" or path.parent == SCRIPT_ROOT:
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
