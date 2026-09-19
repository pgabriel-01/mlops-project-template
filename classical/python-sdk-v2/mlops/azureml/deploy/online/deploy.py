from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

DEPLOYMENT_FINGERPRINT_TAG = "deployment-fingerprint"
REQUEST_SETTINGS = {
    "request_timeout_ms": 60_000,
    "max_concurrent_requests_per_instance": 1,
}
PROBE_SETTINGS = {
    "initial_delay": 10,
    "period": 10,
    "timeout": 2,
    "failure_threshold": 30,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--deployment-name", required=True)
    parser.add_argument("--alternate-deployment-name", required=True)
    parser.add_argument("--traffic-percentage", required=True, type=int)
    parser.add_argument("--lock-storage-account-name", required=True)
    parser.add_argument("--lock-container-name", required=True)
    parser.add_argument("--endpoint-identity-resource-id", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--instance-type", required=True)
    parser.add_argument("--instance-count", required=True, type=int)
    parser.add_argument("--request-file", required=True, type=Path)
    parser.add_argument("--environment-name", default="")
    parser.add_argument("--environment-version", default="")
    parser.add_argument("--environment-image", default="")
    parser.add_argument("--code-directory", type=Path)
    parser.add_argument("--scoring-script", default="")
    parser.add_argument("--mlflow-no-code", action="store_true")
    return parser.parse_args()


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(getattr(value, "value", value)).lower())


def get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def validate_workspace(
    workspace: Any, authoritative_v1_legacy_mode: Any = None
) -> None:
    if normalized(get_field(workspace, "public_network_access", "")) != "disabled":
        raise RuntimeError("The Azure ML workspace must disable public network access")
    sdk_v1_legacy_mode = get_field(workspace, "v1_legacy_mode")
    if sdk_v1_legacy_mode is not False and not (
        sdk_v1_legacy_mode is None and authoritative_v1_legacy_mode is False
    ):
        raise RuntimeError("The Azure ML workspace must not enable v1_legacy_mode")
    managed_network = get_field(workspace, "managed_network")
    isolation_mode = get_field(managed_network, "isolation_mode", "")
    if normalized(isolation_mode) != "allowonlyapprovedoutbound":
        raise RuntimeError(
            "The Azure ML workspace managed network must use "
            "AllowOnlyApprovedOutbound"
        )


def read_workspace_v1_legacy_mode(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
) -> Any:
    resource_id = (
        f"/subscriptions/{quote(subscription_id, safe='')}"
        f"/resourceGroups/{quote(resource_group, safe='')}"
        "/providers/Microsoft.MachineLearningServices/workspaces/"
        f"{quote(workspace_name, safe='')}"
    )
    request = urllib.request.Request(
        "https://management.azure.com" f"{resource_id}?api-version=2024-10-01",
        headers={
            "Authorization": (
                "Bearer "
                + credential.get_token("https://management.azure.com/.default").token
            )
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            workspace = json.load(response)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "Failed to read the authoritative Azure ML workspace ARM state"
        ) from exc
    return get_field(get_field(workspace, "properties", {}), "v1LegacyMode")


def validate_environment_args(args: argparse.Namespace) -> None:
    values = (
        args.environment_name,
        args.environment_version,
        args.environment_image,
    )
    if args.mlflow_no_code and any(values):
        raise ValueError(
            "MLflow no-code mode cannot define an environment name, version, or image"
        )
    if not args.mlflow_no_code and not all(values):
        raise ValueError(
            "Image-only mode requires an environment name, version, and image"
        )
    code_values = (args.code_directory, args.scoring_script)
    if args.mlflow_no_code and any(code_values):
        raise ValueError(
            "MLflow no-code mode cannot define a code directory or scoring script"
        )
    if not args.mlflow_no_code and not all(code_values):
        raise ValueError("Image-only mode requires a code directory and scoring script")
    if args.environment_image and not re.fullmatch(
        r"[a-z0-9]+\.azurecr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
        args.environment_image,
    ):
        raise ValueError("environment-image must use an immutable ACR sha256 digest")
    if args.instance_count < 1:
        raise ValueError("instance-count must be at least one")
    if not 1 <= args.traffic_percentage <= 100:
        raise ValueError("traffic-percentage must be between 1 and 100")
    deployment_name_pattern = r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?"
    for name in (args.deployment_name, args.alternate_deployment_name):
        if not re.fullmatch(deployment_name_pattern, name):
            raise ValueError(
                "deployment names must use 1-32 lowercase letters, numbers, or "
                "hyphens and cannot start or end with a hyphen"
            )
    if args.deployment_name == args.alternate_deployment_name:
        raise ValueError("primary and alternate deployment names must differ")
    if not re.fullmatch(r"[a-z0-9]{3,24}", args.lock_storage_account_name):
        raise ValueError(
            "lock-storage-account-name must be a valid storage account name"
        )
    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?",
        args.lock_container_name,
    ):
        raise ValueError("lock-container-name must be a valid blob container name")
    if not args.request_file.is_file():
        raise ValueError(f"request file does not exist: {args.request_file}")
    if not args.mlflow_no_code:
        code_directory = args.code_directory.resolve()
        scoring_script = Path(args.scoring_script)
        if not code_directory.is_dir():
            raise ValueError(f"code directory does not exist: {code_directory}")
        if scoring_script.is_absolute() or ".." in scoring_script.parts:
            raise ValueError("scoring-script must be relative to code-directory")
        if not (code_directory / scoring_script).is_file():
            raise ValueError(
                f"scoring script does not exist: {code_directory / scoring_script}"
            )


def validate_model_exists(
    client: Any,
    model_name: str,
    model_version: str,
    workspace_name: str,
    resource_not_found_error: type[BaseException],
) -> None:
    try:
        client.models.get(name=model_name, version=model_version)
    except resource_not_found_error as exc:
        raise RuntimeError(
            f"Model '{model_name}:{model_version}' is not registered in Azure ML "
            f"workspace '{workspace_name}'. Register this exact model version "
            "before deploying the online endpoint."
        ) from exc


def code_directory_digest(code_directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(code_directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"code directory cannot contain symlinks: {path}")
        relative_path = path.relative_to(code_directory).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def deployment_fingerprint(args: argparse.Namespace) -> str:
    code_digest = (
        ""
        if args.mlflow_no_code
        else code_directory_digest(args.code_directory.resolve())
    )
    specification = {
        "schema_version": 1,
        "model": {
            "name": args.model_name,
            "version": args.model_version,
        },
        "environment": {
            "mlflow_no_code": args.mlflow_no_code,
            "name": args.environment_name,
            "version": args.environment_version,
            "image": args.environment_image,
        },
        "code": {
            "directory_digest": code_digest,
            "scoring_script": args.scoring_script,
        },
        "compute": {
            "instance_type": args.instance_type,
            "instance_count": args.instance_count,
        },
        "app_insights_enabled": True,
        "request_settings": REQUEST_SETTINGS,
        "readiness_probe": PROBE_SETTINGS,
        "liveness_probe": PROBE_SETTINGS,
    }
    serialized = json.dumps(
        specification,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def select_candidate_deployment(
    deployment_fingerprints: dict[str, str],
    traffic: dict[str, int],
    primary_name: str,
    alternate_name: str,
    desired_fingerprint: str,
) -> str:
    slots = (primary_name, alternate_name)
    for name in slots:
        if deployment_fingerprints.get(name) == desired_fingerprint:
            return name

    active_slots = {name for name, percent in traffic.items() if percent > 0}
    available_slots = [name for name in slots if name not in active_slots]
    if available_slots:
        return available_slots[0]
    raise RuntimeError(
        "Both blue-green deployment slots currently receive traffic. Complete "
        "or roll back the existing promotion before deploying a new model."
    )


def promoted_traffic(
    current_traffic: dict[str, int],
    candidate_name: str,
    traffic_percentage: int,
) -> dict[str, int]:
    if traffic_percentage == 100:
        return {candidate_name: 100}
    previous = [
        name
        for name, percent in current_traffic.items()
        if name != candidate_name and percent > 0
    ]
    if len(previous) != 1:
        raise RuntimeError(
            "Partial traffic promotion requires exactly one previously serving "
            "deployment."
        )
    return {
        previous[0]: 100 - traffic_percentage,
        candidate_name: traffic_percentage,
    }


def deploy_under_lock(
    args: argparse.Namespace,
    client: Any,
    sdk: SimpleNamespace,
    resource_not_found_error: type[BaseException],
    lease: Any,
) -> None:
    desired_fingerprint = deployment_fingerprint(args)
    lease.ensure_held()
    existing_endpoint = None
    try:
        existing_endpoint = client.online_endpoints.get(args.endpoint_name)
    except resource_not_found_error:
        pass

    endpoint_identity = sdk.IdentityConfiguration(
        type="user_assigned",
        user_assigned_identities=[
            sdk.ManagedIdentityConfiguration(
                resource_id=args.endpoint_identity_resource_id
            )
        ],
    )
    if existing_endpoint is not None:
        existing_identities = {
            identity.resource_id
            for identity in (existing_endpoint.identity.user_assigned_identities or [])
        }
        if existing_identities != {args.endpoint_identity_resource_id}:
            raise RuntimeError(
                "Managed online endpoint identity is immutable; replace the "
                "endpoint to change its user-assigned identity"
            )

    endpoint = sdk.ManagedOnlineEndpoint(
        name=args.endpoint_name,
        description="Private Azure ML managed online endpoint",
        auth_mode="aad_token",
        public_network_access="disabled",
        identity=endpoint_identity,
        traffic=existing_endpoint.traffic if existing_endpoint else None,
        tags={
            "managed-by": "python-sdk-v2",
            "network-access": "private",
        },
    )
    client.online_endpoints.begin_create_or_update(endpoint).result()

    environment_reference = None
    code_configuration = None
    if not args.mlflow_no_code:
        environment = sdk.Environment(
            name=args.environment_name,
            version=args.environment_version,
            image=args.environment_image,
            description="Immutable managed online endpoint environment",
        )
        client.environments.create_or_update(environment)
        environment_reference = (
            f"azureml:{args.environment_name}:{args.environment_version}"
        )
        code_configuration = sdk.CodeConfiguration(
            code=str(args.code_directory.resolve()),
            scoring_script=args.scoring_script,
        )

    current_traffic = dict(existing_endpoint.traffic or {}) if existing_endpoint else {}
    deployment_fingerprints: dict[str, str] = {}
    for deployment_name in (
        args.deployment_name,
        args.alternate_deployment_name,
    ):
        try:
            existing_deployment = client.online_deployments.get(
                name=deployment_name,
                endpoint_name=args.endpoint_name,
            )
        except resource_not_found_error:
            continue
        deployment_fingerprints[deployment_name] = str(
            (existing_deployment.tags or {}).get(DEPLOYMENT_FINGERPRINT_TAG, "")
        )
    candidate_name = select_candidate_deployment(
        deployment_fingerprints=deployment_fingerprints,
        traffic=current_traffic,
        primary_name=args.deployment_name,
        alternate_name=args.alternate_deployment_name,
        desired_fingerprint=desired_fingerprint,
    )

    deployment = sdk.ManagedOnlineDeployment(
        name=candidate_name,
        endpoint_name=args.endpoint_name,
        model=f"azureml:{args.model_name}:{args.model_version}",
        environment=environment_reference,
        code_configuration=code_configuration,
        instance_type=args.instance_type,
        instance_count=args.instance_count,
        app_insights_enabled=True,
        tags={
            DEPLOYMENT_FINGERPRINT_TAG: desired_fingerprint,
            "model-version": args.model_version,
        },
        request_settings=sdk.OnlineRequestSettings(
            **REQUEST_SETTINGS,
        ),
        readiness_probe=sdk.ProbeSettings(**PROBE_SETTINGS),
        liveness_probe=sdk.ProbeSettings(**PROBE_SETTINGS),
    )
    client.online_deployments.begin_create_or_update(deployment).result()

    lease.ensure_held()
    live_deployment = client.online_deployments.get(
        name=candidate_name,
        endpoint_name=args.endpoint_name,
    )
    if normalized(live_deployment.provisioning_state) != "succeeded":
        raise RuntimeError(
            f"Deployment provisioning state is {live_deployment.provisioning_state}"
        )

    client.online_endpoints.invoke(
        endpoint_name=args.endpoint_name,
        deployment_name=candidate_name,
        request_file=str(args.request_file),
    )

    lease.ensure_held()
    live_endpoint = client.online_endpoints.get(args.endpoint_name)
    live_endpoint.traffic = promoted_traffic(
        current_traffic=dict(live_endpoint.traffic or {}),
        candidate_name=candidate_name,
        traffic_percentage=args.traffic_percentage,
    )
    client.online_endpoints.begin_create_or_update(live_endpoint).result()


def deploy(args: argparse.Namespace) -> None:
    from azure.ai.ml import MLClient
    from azure.ai.ml.entities import (
        CodeConfiguration,
        Environment,
        IdentityConfiguration,
        ManagedIdentityConfiguration,
        ManagedOnlineDeployment,
        ManagedOnlineEndpoint,
        OnlineRequestSettings,
        ProbeSettings,
    )
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import DefaultAzureCredential

    from deployment_lock import endpoint_deployment_lock

    validate_environment_args(args)
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = MLClient(
        credential=credential,
        subscription_id=args.subscription_id,
        resource_group_name=args.resource_group,
        workspace_name=args.workspace_name,
    )
    workspace = client.workspaces.get(args.workspace_name)
    sdk_v1_legacy_mode = get_field(workspace, "v1_legacy_mode")
    authoritative_v1_legacy_mode = None
    if sdk_v1_legacy_mode is None:
        authoritative_v1_legacy_mode = read_workspace_v1_legacy_mode(
            credential=credential,
            subscription_id=args.subscription_id,
            resource_group=args.resource_group,
            workspace_name=args.workspace_name,
        )
    validate_workspace(workspace, authoritative_v1_legacy_mode)
    validate_model_exists(
        client=client,
        model_name=args.model_name,
        model_version=args.model_version,
        workspace_name=args.workspace_name,
        resource_not_found_error=ResourceNotFoundError,
    )
    sdk = SimpleNamespace(
        CodeConfiguration=CodeConfiguration,
        Environment=Environment,
        IdentityConfiguration=IdentityConfiguration,
        ManagedIdentityConfiguration=ManagedIdentityConfiguration,
        ManagedOnlineDeployment=ManagedOnlineDeployment,
        ManagedOnlineEndpoint=ManagedOnlineEndpoint,
        OnlineRequestSettings=OnlineRequestSettings,
        ProbeSettings=ProbeSettings,
    )
    with endpoint_deployment_lock(
        credential=credential,
        storage_account_name=args.lock_storage_account_name,
        container_name=args.lock_container_name,
        endpoint_name=args.endpoint_name,
    ) as lease:
        deploy_under_lock(
            args=args,
            client=client,
            sdk=sdk,
            resource_not_found_error=ResourceNotFoundError,
            lease=lease,
        )


def main() -> None:
    deploy(parse_args())


if __name__ == "__main__":
    main()
