from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from project_config import load_config

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
RUNNER_HUB_ID_PATTERN = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+$",
    re.IGNORECASE,
)
AZURE_COMMAND_TIMEOUT_SECONDS = 120
RESOURCE_GRAPH_SUBSCRIPTION_BATCH_SIZE = 1000


def az_json(*args: str) -> Any:
    try:
        result = subprocess.run(
            ["az", *args, "--only-show-errors", "--output", "json"],
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


def find_runner_hub_zone_links(runner_hub_vnet_id: str) -> list[dict[str, str]]:
    subscriptions = [
        subscription["id"]
        for subscription in az_json("account", "list")
        if subscription.get("state") == "Enabled"
    ]
    if not subscriptions:
        raise RuntimeError("No enabled Azure subscriptions are available")
    escaped_hub_id = runner_hub_vnet_id.replace("'", "''")
    query = f"""
resources
| where type =~ 'microsoft.network/privatednszones/virtualnetworklinks'
| where tostring(properties.virtualNetwork.id) =~ '{escaped_hub_id}'
| extend zoneId = substring(id, 0, indexof(id, '/virtualNetworkLinks/'))
| extend zoneName = tostring(split(id, '/')[8])
| project zoneName, zoneId
"""
    links: list[dict[str, str]] = []
    for start in range(0, len(subscriptions), RESOURCE_GRAPH_SUBSCRIPTION_BATCH_SIZE):
        subscription_batch = subscriptions[
            start : start + RESOURCE_GRAPH_SUBSCRIPTION_BATCH_SIZE
        ]
        skip_token = ""
        while True:
            options = {"resultFormat": "objectArray", "$top": 1000}
            if skip_token:
                options["$skipToken"] = skip_token
            response = az_json(
                "rest",
                "--method",
                "post",
                "--url",
                (
                    "https://management.azure.com/providers/Microsoft.ResourceGraph/"
                    "resources?api-version=2022-10-01"
                ),
                "--body",
                json.dumps(
                    {
                        "subscriptions": subscription_batch,
                        "query": query,
                        "options": options,
                    }
                ),
            )
            links.extend(response.get("data", []))
            skip_token = response.get("$skipToken") or response.get("skipToken") or ""
            if not skip_token:
                break
    return links


def find_blockers(config: dict[str, object]) -> list[str]:
    runner_hub_vnet_id = str(config.get("runner_hub_vnet_resource_id", "")).strip()
    try:
        supplied = json.loads(
            str(config.get("shared_private_dns_zone_resource_ids", "{}"))
        )
    except json.JSONDecodeError:
        return ["shared_private_dns_zone_resource_ids must be a JSON object"]
    if not isinstance(supplied, dict):
        return ["shared_private_dns_zone_resource_ids must be a JSON object"]
    if not runner_hub_vnet_id:
        return (
            []
            if not supplied
            else ["shared private DNS zones require a runner hub VNet resource ID"]
        )
    if not RUNNER_HUB_ID_PATTERN.fullmatch(runner_hub_vnet_id):
        return ["runner_hub_vnet_resource_id is not a valid Azure VNet resource ID"]
    for zone_name, zone_id in supplied.items():
        expected_suffix = f"/providers/Microsoft.Network/privateDnsZones/{zone_name}"
        if (
            not isinstance(zone_name, str)
            or zone_name not in PRIVATE_DNS_ZONE_NAMES
            or not isinstance(zone_id, str)
            or not zone_id.lower().endswith(expected_suffix.lower())
            or not re.match(
                r"^/subscriptions/[^/]+/resourceGroups/[^/]+/",
                zone_id,
                re.IGNORECASE,
            )
        ):
            return [f"invalid shared private DNS zone mapping for {zone_name}"]

    linked_by_name: dict[str, list[str]] = {}
    for link in find_runner_hub_zone_links(runner_hub_vnet_id):
        zone_name = str(link.get("zoneName", "")).lower()
        zone_id = str(link.get("zoneId", ""))
        if zone_name in PRIVATE_DNS_ZONE_NAMES:
            linked_by_name.setdefault(zone_name, []).append(zone_id)

    blockers: list[str] = []
    for zone_name, zone_ids in sorted(linked_by_name.items()):
        unique_ids = {zone_id.lower(): zone_id for zone_id in zone_ids}
        if len(unique_ids) != 1:
            blockers.append(
                f"runner hub has multiple authoritative {zone_name} zones: "
                + ", ".join(sorted(unique_ids.values()))
            )
            continue
        linked_zone_id = next(iter(unique_ids.values()))
        supplied_zone_id = supplied.get(zone_name)
        if supplied_zone_id is None:
            blockers.append(
                f"shared_private_dns_zone_resource_ids must include {zone_name}: "
                f"{linked_zone_id}"
            )
        elif str(supplied_zone_id).lower() != linked_zone_id.lower():
            blockers.append(
                f"configured {zone_name} zone does not match the runner hub link: "
                f"expected {linked_zone_id}, got {supplied_zone_id}"
            )

    for zone_name, supplied_zone_id in sorted(supplied.items()):
        if zone_name not in linked_by_name:
            blockers.append(
                f"configured {zone_name} zone is not linked to the runner hub: "
                f"{supplied_zone_id}"
            )
    return blockers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_file", type=Path)
    args = parser.parse_args()
    try:
        blockers = find_blockers(load_config(args.config_file))
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        raise SystemExit(f"Runner hub private DNS preflight failed: {error}") from error
    if blockers:
        raise SystemExit(
            "Runner hub private DNS preflight failed:\n- " + "\n- ".join(blockers)
        )
    print("Runner hub private DNS ownership matches the supplied zone map.")


if __name__ == "__main__":
    main()
