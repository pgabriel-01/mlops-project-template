import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_runner_subnet.py"
SPEC = importlib.util.spec_from_file_location("validate_runner_subnet", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def vnet(*subnets):
    return {
        "addressPrefixes": ["10.240.0.0/16"],
        "subnets": list(subnets),
    }


def subnet(name, prefix, **overrides):
    value = {
        "name": name,
        "prefix": prefix,
        "delegations": [],
        "privateEndpointNetworkPolicies": "Enabled",
        "privateLinkServiceNetworkPolicies": "Enabled",
    }
    value.update(overrides)
    return value


class ValidateRunnerSubnetTests(unittest.TestCase):
    def test_accepts_absent_runner_subnet(self):
        message = MODULE.validate_runner_subnet(
            "10.240.2.0/24",
            "snet-github-runners",
            vnet(subnet("snet-mdp", "10.240.0.0/24")),
        )
        self.assertIn("is available", message)

    def test_accepts_exact_existing_managed_subnet(self):
        message = MODULE.validate_runner_subnet(
            "10.240.2.0/24",
            "snet-github-runners",
            vnet(subnet("snet-github-runners", "10.240.2.0/24")),
        )
        self.assertIn("already exists", message)

    def test_rejects_same_name_with_different_prefix(self):
        with self.assertRaisesRegex(ValueError, "expected 10.240.2.0/24"):
            MODULE.validate_runner_subnet(
                "10.240.2.0/24",
                "snet-github-runners",
                vnet(subnet("snet-github-runners", "10.240.3.0/24")),
            )

    def test_rejects_overlap_with_another_subnet(self):
        with self.assertRaisesRegex(ValueError, "overlaps existing subnet other"):
            MODULE.validate_runner_subnet(
                "10.240.2.0/24",
                "snet-github-runners",
                vnet(subnet("other", "10.240.2.0/25")),
            )

    def test_rejects_incompatible_existing_managed_subnet(self):
        with self.assertRaisesRegex(ValueError, "incompatible delegations"):
            MODULE.validate_runner_subnet(
                "10.240.2.0/24",
                "snet-github-runners",
                vnet(
                    subnet(
                        "snet-github-runners",
                        "10.240.2.0/24",
                        delegations=["Microsoft.DevOpsInfrastructure/pools"],
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
