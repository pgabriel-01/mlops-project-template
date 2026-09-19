from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

AZURE_COMMAND_TIMEOUT_SECONDS = 120


def az_json(*args: str) -> Any:
    try:
        result = subprocess.run(
            ["az", *args, "--output", "json", "--only-show-errors"],
            check=True,
            capture_output=True,
            text=True,
            timeout=AZURE_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Azure CLI command timed out after {AZURE_COMMAND_TIMEOUT_SECONDS} "
            f"seconds: az {' '.join(args)}"
        ) from error
    return json.loads(result.stdout)


def is_desired_private_bastion(bastion: dict[str, Any], expected_name: str) -> bool:
    ip_configurations = bastion.get("ipConfigurations") or []
    if len(ip_configurations) != 1:
        return False
    ip_configuration = ip_configurations[0]
    subnet_id = ((ip_configuration.get("subnet") or {}).get("id") or "").lower()
    has_public_ip = any(
        ip_configuration.get(key) is not None
        for key in ("publicIpAddress", "publicIPAddress")
    )
    return (
        bastion.get("name") == expected_name
        and (bastion.get("sku") or {}).get("name") == "Premium"
        and bastion.get("provisioningState") == "Succeeded"
        and bastion.get("enablePrivateOnlyBastion") is not False
        and bastion.get("enableTunneling") is True
        and ip_configuration.get("name") == "private"
        and ip_configuration.get("privateIPAllocationMethod") == "Dynamic"
        and ip_configuration.get("provisioningState") == "Succeeded"
        and subnet_id.endswith("/subnets/azurebastionsubnet")
        and not has_public_ip
    )


def find_blockers(resource_group: str, base_name: str) -> list[str]:
    if not az_json("group", "exists", "--name", resource_group):
        return []

    expected_name = f"bastion-private-{base_name}"
    blockers: list[str] = []
    for bastion in az_json(
        "network", "bastion", "list", "--resource-group", resource_group
    ):
        name = bastion.get("name", "")
        if not is_desired_private_bastion(bastion, expected_name):
            blockers.append(f"Bastion {name or '<unnamed>'}")

    legacy_names = {
        f"pip-bastion-{base_name}",
        f"vm-jumpbox-{base_name}",
        f"nic-jumpbox-{base_name}",
        f"nsg-jumpbox-{base_name}",
    }
    for resource in az_json("resource", "list", "--resource-group", resource_group):
        if resource.get("name") in legacy_names:
            blockers.append(f"{resource.get('type')} {resource['name']}")
    return sorted(set(blockers))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--base-name", required=True)
    args = parser.parse_args()

    try:
        blockers = find_blockers(args.resource_group, args.base_name)
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise SystemExit(f"Private Bastion preflight failed: {error}") from error
    if blockers:
        details = "\n".join(f"- {blocker}" for blocker in blockers)
        raise SystemExit(
            "Legacy public Bastion/jumpbox resources block the private-only "
            "replacement:\n"
            f"{details}\n"
            "Confirm there are no active Bastion sessions, explicitly remove "
            "the legacy Bastion and its public IP plus the retired Windows "
            "jumpbox assets, then rerun deployment. Azure permits only one "
            "Bastion per VNet/AzureBastionSubnet."
        )


if __name__ == "__main__":
    main()
