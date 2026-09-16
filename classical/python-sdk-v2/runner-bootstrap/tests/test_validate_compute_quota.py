import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "validate_compute_quota.py"
)
SPEC = importlib.util.spec_from_file_location("validate_compute_quota", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ValidateComputeQuotaTests(unittest.TestCase):
    def setUp(self):
        self.sku = [
            {
                "name": "Standard_D2ads_v6",
                "family": "standardDADSv6Family",
                "capabilities": [{"name": "vCPUs", "value": "2"}],
                "restrictions": [],
            }
        ]
        self.usages = [
            {"name": {"value": "cores"}, "currentValue": 10, "limit": 20},
            {
                "name": {"value": "standardDADSv6Family"},
                "currentValue": 2,
                "limit": 10,
            },
        ]

    def test_accepts_sufficient_total_and_family_quota(self):
        result = MODULE.validate_compute_quota(
            "Standard_D2ads_v6", 2, self.sku, self.usages
        )

        self.assertEqual(result["required_vcpus"], 4)
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(result["family"], "standardDADSv6Family")

    def test_rejects_insufficient_total_regional_quota(self):
        self.usages[0]["currentValue"] = 19

        with self.assertRaisesRegex(ValueError, "Total Regional vCPUs quota"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_insufficient_family_quota(self):
        self.usages[1]["currentValue"] = 9

        with self.assertRaisesRegex(ValueError, "VM family 'standardDADSv6Family'"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_derives_required_vcpus_from_node_count_and_sku(self):
        self.sku[0]["capabilities"][0]["value"] = "4"
        self.usages[0]["limit"] = 30
        self.usages[1]["limit"] = 30

        result = MODULE.validate_compute_quota(
            "Standard_D2ads_v6", 3, self.sku, self.usages
        )

        self.assertEqual(result["required_vcpus"], 12)

    def test_rejects_missing_sku_family_metadata(self):
        self.sku[0]["family"] = None

        with self.assertRaisesRegex(ValueError, "missing familyName"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_missing_sku_vcpu_metadata(self):
        self.sku[0]["capabilities"] = []

        with self.assertRaisesRegex(ValueError, "exactly one vCPUs capability"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_restricted_sku(self):
        self.sku[0]["restrictions"] = [{"type": "Location"}]

        with self.assertRaisesRegex(ValueError, "has subscription restrictions"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_ambiguous_exact_sku_results(self):
        self.sku.append(self.sku[0].copy())

        with self.assertRaisesRegex(ValueError, "exactly one Azure SKU result"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_missing_exact_family_quota(self):
        self.usages.pop()

        with self.assertRaisesRegex(
            ValueError, "name.value 'standardDADSv6Family'"
        ):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )

    def test_rejects_missing_total_regional_quota(self):
        self.usages.pop(0)

        with self.assertRaisesRegex(ValueError, "name.value 'cores'"):
            MODULE.validate_compute_quota(
                "Standard_D2ads_v6", 1, self.sku, self.usages
            )


if __name__ == "__main__":
    unittest.main()
