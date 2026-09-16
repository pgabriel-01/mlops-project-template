#!/usr/bin/env python3
"""Validate that the ARC subnet is absent or an idempotent managed match."""

from __future__ import annotations

import ipaddress
import json
import sys
from typing import Any


def validate_runner_subnet(
    candidate_prefix: str,
    runner_subnet_name: str,
    vnet: dict[str, Any],
) -> str:
    candidate = ipaddress.ip_network(candidate_prefix)
    spaces = [
        ipaddress.ip_network(value)
        for value in vnet.get("addressPrefixes", [])
    ]
    if not any(candidate.subnet_of(space) for space in spaces):
        raise ValueError(
            f"{candidate} is not contained by the hub VNet address space"
        )

    managed_subnet_found = False
    for subnet in vnet.get("subnets", []):
        name = str(subnet["name"])
        existing = ipaddress.ip_network(str(subnet["prefix"]))
        if name == runner_subnet_name:
            if existing != candidate:
                raise ValueError(
                    f"{runner_subnet_name} uses {existing}; expected {candidate}"
                )
            delegations = [
                value for value in subnet.get("delegations", []) if value
            ]
            if delegations:
                raise ValueError(
                    f"{runner_subnet_name} has incompatible delegations: "
                    f"{', '.join(delegations)}"
                )
            for field in (
                "privateEndpointNetworkPolicies",
                "privateLinkServiceNetworkPolicies",
            ):
                value = subnet.get(field)
                if value not in {None, "Enabled"}:
                    raise ValueError(
                        f"{runner_subnet_name} has incompatible {field}: {value}"
                    )
            managed_subnet_found = True
        elif candidate.overlaps(existing):
            raise ValueError(
                f"{candidate} overlaps existing subnet {name} ({existing})"
            )

    if managed_subnet_found:
        return (
            f"Runner subnet {runner_subnet_name} already exists with compatible "
            f"prefix {candidate}"
        )
    return f"Runner subnet {candidate} is available"


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: validate_runner_subnet.py "
            "<candidate-prefix> <runner-subnet-name> <vnet-json>"
        )
    try:
        message = validate_runner_subnet(
            sys.argv[1],
            sys.argv[2],
            json.loads(sys.argv[3]),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(message)


if __name__ == "__main__":
    main()
