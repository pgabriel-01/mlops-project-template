import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_config import load_config

class ProjectContractTests(unittest.TestCase):
    def test_generated_tree_and_workflow_contract(self):
        subprocess.run(
            [sys.executable, "scripts/validate_project.py"],
            cwd=ROOT,
            check=True,
        )

    def test_private_configs_use_self_hosted_runner_labels(self):
        for environment in ("dev", "test", "prod"):
            config = load_config(ROOT / f"config-infra-{environment}.yml")
            self.assertTrue(config["private_network"])
            self.assertEqual("mlops-private", config["runner"])

    def test_reusable_workflows_use_generator_placeholders(self):
        workflows = {
            "train-register-model.yml": "python-sdk-v2-train-register.yml",
            "deploy-online-endpoint.yml": "python-sdk-v2-online.yml",
            "deploy-batch-endpoint.yml": "python-sdk-v2-batch.yml",
        }
        for caller_name, reusable_name in workflows.items():
            content = (
                ROOT / ".github" / "workflows" / caller_name
            ).read_text()
            expected = (
                "__MLOPS_TEMPLATES_REPOSITORY__/.github/workflows/"
                f"{reusable_name}@__MLOPS_TEMPLATES_REF__"
            )
            self.assertIn(expected, content)
            self.assertIn(
                "sdk_repository: __MLOPS_TEMPLATES_REPOSITORY__", content
            )
            self.assertIn("sdk_ref: __MLOPS_TEMPLATES_REF__", content)

    def test_known_template_pin_resolves_all_placeholders(self):
        repository = "pgabriel-01/mlops-templates"
        commit = "be9755ccfc320fd1f2c1fb4f6b092d745d4fa6b5"
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            rendered = (
                path.read_text()
                .replace("__MLOPS_TEMPLATES_REPOSITORY__", repository)
                .replace("__MLOPS_TEMPLATES_REF__", commit)
            )
            self.assertNotIn("__MLOPS_TEMPLATES_", rendered)
        self.assertEqual(40, len(commit))

    def test_bicep_preserves_keyless_private_storage_contract(self):
        storage = (
            ROOT / "infrastructure/bicep/modules/storage_account.bicep"
        ).read_text()
        workspace = (
            ROOT / "infrastructure/bicep/modules/aml_workspace.bicep"
        ).read_text()
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()
        dns = (
            ROOT / "infrastructure/bicep/modules/private_dns_zones.bicep"
        ).read_text()

        self.assertIn("allowSharedKeyAccess: false", storage)
        self.assertIn("systemDatastoresAuthMode: 'identity'", workspace)
        self.assertIn("managedNetwork:", workspace)
        self.assertIn("enableNodePublicIp: empty(subnetId)", (
            ROOT / "infrastructure/bicep/modules/aml_computecluster.bicep"
        ).read_text())
        self.assertNotIn("adoServicePrincipalId", main + workspace)
        self.assertIn("ciPrincipalObjectId", main + workspace)
        for service in ("blob", "file", "queue", "table"):
            self.assertIn(f"groupId: '{service}'", main)
            self.assertIn(f"privatelink.{service}.", dns)
        self.assertIn("dnsZones!.outputs.amlDnsZoneId", main)
        self.assertIn("dnsZones!.outputs.notebookDnsZoneId", main)


if __name__ == "__main__":
    unittest.main()
