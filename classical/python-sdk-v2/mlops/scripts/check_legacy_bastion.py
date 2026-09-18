from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any


def az_json(*args: str) -> Any:
    result = subprocess.run(
        ["az", *args, "--output", "json", "--only-show-errors"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def find_blockers(resource_group: str, base_name: str) -> list[str]:
    if not az_json("group", "exists", "--name", resource_group):
        return []

    expected_name = f"bastion-private-{base_name}"
    blockers: list[str] = []
    for bastion in az_json(
        "network", "bastion", "list", "--resource-group", resource_group
    ):
        name = bastion.get("name", "")
        sku = (bastion.get("sku") or {}).get("name")
        private_only = bastion.get("enablePrivateOnlyBastion")
        if name != expected_name or sku != "Premium" or private_only is not True:
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

    blockers = find_blockers(args.resource_group, args.base_name)
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
