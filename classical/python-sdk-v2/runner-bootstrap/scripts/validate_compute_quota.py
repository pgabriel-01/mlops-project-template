#!/usr/bin/env python3
import json
import sys
from typing import Any


def _positive_integer(value: Any, description: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{description} must be a positive integer") from error
    if number <= 0:
        raise ValueError(f"{description} must be a positive integer")
    return number


def _usage_entry(usages: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [
        usage
        for usage in usages
        if isinstance(usage.get("name"), dict) and usage["name"].get("value") == name
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Azure quota entry with name.value '{name}'")
    return matches[0]


def validate_compute_quota(
    node_sku: str,
    node_count: Any,
    sku_results: Any,
    usages: Any,
) -> dict[str, Any]:
    count = _positive_integer(node_count, "System node count")
    if not isinstance(sku_results, list):
        raise ValueError("Azure SKU response must be a JSON array")

    matches = [
        sku
        for sku in sku_results
        if isinstance(sku, dict) and sku.get("name") == node_sku
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Azure SKU result for '{node_sku}'")

    sku = matches[0]
    restrictions = sku.get("restrictions")
    if restrictions is None:
        raise ValueError(f"Azure SKU metadata for '{node_sku}' is missing restrictions")
    if restrictions:
        raise ValueError(
            f"Node SKU '{node_sku}' has subscription restrictions: "
            f"{json.dumps(restrictions, separators=(',', ':'))}"
        )

    family = sku.get("family")
    if not isinstance(family, str) or not family:
        raise ValueError(f"Azure SKU metadata for '{node_sku}' is missing familyName")

    capabilities = sku.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError(f"Azure SKU metadata for '{node_sku}' is missing capabilities")
    vcpu_capabilities = [
        capability
        for capability in capabilities
        if isinstance(capability, dict) and capability.get("name") == "vCPUs"
    ]
    if len(vcpu_capabilities) != 1:
        raise ValueError(
            f"Expected exactly one vCPUs capability for Azure SKU '{node_sku}'"
        )
    sku_vcpus = _positive_integer(
        vcpu_capabilities[0].get("value"), f"vCPUs capability for '{node_sku}'"
    )
    required_vcpus = sku_vcpus * count

    if not isinstance(usages, list):
        raise ValueError("Azure usage response must be a JSON array")

    quota_results = {}
    for quota_name, description in (
        ("cores", "Total Regional vCPUs"),
        (family, f"VM family '{family}'"),
    ):
        usage = _usage_entry(usages, quota_name)
        current = _positive_integer_or_zero(
            usage.get("currentValue"), f"{description} current usage"
        )
        limit = _positive_integer(usage.get("limit"), f"{description} quota limit")
        remaining = limit - current
        if remaining < required_vcpus:
            raise ValueError(
                f"{description} quota has {remaining} vCPUs remaining, "
                f"but {required_vcpus} are required for {count} x {node_sku} "
                f"({sku_vcpus} vCPUs each)"
            )
        quota_results[quota_name] = remaining

    return {
        "family": family,
        "node_count": count,
        "required_vcpus": required_vcpus,
        "sku_vcpus": sku_vcpus,
        "total_remaining": quota_results["cores"],
        "family_remaining": quota_results[family],
    }


def _positive_integer_or_zero(value: Any, description: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{description} must be a non-negative integer") from error
    if number < 0:
        raise ValueError(f"{description} must be a non-negative integer")
    return number


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "Usage: validate_compute_quota.py NODE_SKU NODE_COUNT SKU_JSON USAGE_JSON"
        )

    try:
        result = validate_compute_quota(
            sys.argv[1],
            sys.argv[2],
            json.loads(sys.argv[3]),
            json.loads(sys.argv[4]),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Compute quota validation failed: {error}") from error

    print(
        f"Compute quota headroom: {result['required_vcpus']} vCPUs required; "
        f"{result['total_remaining']} regional and "
        f"{result['family_remaining']} in {result['family']} remain"
    )


if __name__ == "__main__":
    main()
