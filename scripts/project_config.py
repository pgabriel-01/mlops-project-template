from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"{path}:{line_number}: expected key: value")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or not value:
            raise ValueError(f"{path}:{line_number}: key and value are required")
        if value in {"true", "false"}:
            parsed: Any = value == "true"
        elif value.startswith('"') and value.endswith('"'):
            parsed = json.loads(value)
        elif value.isdigit():
            parsed = int(value)
        else:
            parsed = value
        config[key] = parsed
    return config


def derive_config(config: dict[str, Any]) -> dict[str, Any]:
    base_name = (
        f"{config['namespace']}-{config['postfix']}"
        f"{config['project_number']}{config['environment']}"
    )
    compact_name = (
        f"{config['namespace']}{config['postfix']}"
        f"{config['project_number']}{config['environment']}"
    )
    return {
        **config,
        "resource_group": f"rg-{base_name}",
        "workspace_name": f"mlw-{base_name}",
        "online_endpoint_name": (
            f"{config['online_endpoint_suffix']}-{compact_name}"
        )[:32],
        "batch_endpoint_name": (
            f"{config['batch_endpoint_suffix']}-{compact_name}"
        )[:32],
    }
