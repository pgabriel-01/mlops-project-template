from __future__ import annotations

import argparse
import re
from pathlib import Path

from project_config import load_config


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("dev", "test", "prod")
REQUIRED_CONFIG = {
    "environment",
    "location",
    "namespace",
    "postfix",
    "project_number",
    "private_network",
    "runner",
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


def validate_tree() -> list[str]:
    errors: list[str] = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if FORBIDDEN_PATH_PARTS.intersection(relative.parts):
            errors.append(f"forbidden generated path: {relative}")
    return errors


def validate_configs() -> list[str]:
    errors: list[str] = []
    for environment in ENVIRONMENTS:
        path = ROOT / f"config-infra-{environment}.yml"
        config = load_config(path)
        missing = REQUIRED_CONFIG - config.keys()
        if missing:
            errors.append(f"{path.name} missing: {', '.join(sorted(missing))}")
        if config.get("environment") != environment:
            errors.append(f"{path.name} has wrong environment")
        if config.get("private_network") and config.get("runner") in {
            "ubuntu-latest",
            "ubuntu-24.04",
        }:
            errors.append(f"{path.name} private network requires a private runner")
    return errors


def validate_workflows(require_resolved_templates: bool) -> list[str]:
    errors: list[str] = []
    workflow_dir = ROOT / ".github" / "workflows"
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
    scan_roots = (
        ROOT / ".github" / "workflows",
        ROOT / "classical" / "python-sdk-v2",
        ROOT / "infrastructure" / "bicep",
        ROOT / "README.md",
        ROOT / "classical" / "README.md",
    )
    for scan_root in scan_roots:
        paths = [scan_root] if scan_root.is_file() else scan_root.rglob("*")
        for path in paths:
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
