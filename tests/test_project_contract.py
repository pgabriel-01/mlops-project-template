import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
sys.path.insert(0, str(ROOT / "scripts"))

from project_config import load_config
from validate_project import validate_config_values


class ProjectContractTests(unittest.TestCase):
    def test_generated_tree_and_workflow_contract(self):
        subprocess.run(
            [sys.executable, "scripts/validate_project.py"],
            cwd=ROOT,
            check=True,
        )

    def test_private_configs_use_self_hosted_runner_labels(self):
        for environment in ("dev", "test", "prod"):
            config = load_config(PATTERN_ROOT / f"config-infra-{environment}.yml")
            self.assertTrue(config["private_network"])
            self.assertEqual("mlops-private", config["runner"])
            self.assertEqual("", config["runner_hub_vnet_resource_id"])
            self.assertFalse(config["manage_runner_hub_to_workload_peering"])

    def test_runner_hub_parameters_render_in_disabled_and_enabled_modes(self):
        script = ROOT / "scripts" / "render_bicep_parameters.py"
        base_config = (PATTERN_ROOT / "config-infra-dev.yml").read_text()
        runner_hub_id = (
            "/subscriptions/subscription-id/"
            "resourceGroups/runner-network/providers/Microsoft.Network/"
            "virtualNetworks/runner-hub"
        )
        cases = (
            (base_config, "", False),
            (
                base_config.replace(
                    'runner_hub_vnet_resource_id: ""',
                    f'runner_hub_vnet_resource_id: "{runner_hub_id}"',
                ).replace(
                    "manage_runner_hub_to_workload_peering: false",
                    "manage_runner_hub_to_workload_peering: true",
                ),
                runner_hub_id,
                True,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            for index, (config_text, expected_id, expected_manage) in enumerate(
                cases
            ):
                config_path = directory_path / "config-infra-dev.yml"
                output_path = directory_path / f"parameters-{index}.json"
                config_path.write_text(config_text)
                subprocess.run(
                    [sys.executable, script, config_path, output_path],
                    check=True,
                    env={
                        **os.environ,
                        "AZURE_PRINCIPAL_OBJECT_ID": (
                            "00000000-0000-0000-0000-000000000001"
                        ),
                    },
                )
                parameters = json.loads(output_path.read_text())["parameters"]
                self.assertEqual(
                    expected_id,
                    parameters["runnerHubVnetResourceId"]["value"],
                )
                self.assertEqual(
                    expected_manage,
                    parameters["manageRunnerHubToWorkloadPeering"]["value"],
                )
                self.assertEqual(
                    [],
                    validate_config_values(config_path, load_config(config_path)),
                )

    def test_runner_hub_config_validation_rejects_inconsistent_modes(self):
        config = load_config(PATTERN_ROOT / "config-infra-dev.yml")
        path = Path("config-infra-dev.yml")
        runner_hub_id = (
            "/subscriptions/subscription-id/"
            "resourceGroups/runner-network/providers/Microsoft.Network/"
            "virtualNetworks/runner-hub"
        )

        invalid_resource_id = dict(config)
        invalid_resource_id["runner_hub_vnet_resource_id"] = "runner-hub"
        self.assertTrue(validate_config_values(path, invalid_resource_id))

        missing_hub = dict(config)
        missing_hub["manage_runner_hub_to_workload_peering"] = True
        self.assertTrue(validate_config_values(path, missing_hub))

        disabled_vnet = dict(config)
        disabled_vnet["runner_hub_vnet_resource_id"] = runner_hub_id
        disabled_vnet["enable_vnet"] = False
        self.assertTrue(validate_config_values(path, disabled_vnet))

    def test_reusable_workflows_use_generator_placeholders(self):
        workflows = {
            "train-register-model.yml": "python-sdk-v2-train-register.yml",
            "deploy-online-endpoint.yml": "python-sdk-v2-online.yml",
            "deploy-batch-endpoint.yml": "python-sdk-v2-batch.yml",
        }
        for caller_name, reusable_name in workflows.items():
            content = (
                PATTERN_ROOT / "mlops" / "github-actions" / caller_name
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
        for path in (PATTERN_ROOT / "mlops" / "github-actions").glob("*.yml"):
            rendered = (
                path.read_text()
                .replace("__MLOPS_TEMPLATES_REPOSITORY__", repository)
                .replace("__MLOPS_TEMPLATES_REF__", commit)
            )
            self.assertNotIn("__MLOPS_TEMPLATES_", rendered)
        self.assertEqual(40, len(commit))

    def test_readme_documents_environment_oidc_bootstrap(self):
        readme = (PATTERN_ROOT / "README.md").read_text()
        for required in (
            "https://token.actions.githubusercontent.com",
            "api://AzureADTokenExchange",
            "repo:<owner>/<repo>:environment:dev",
            "repo:<owner>/<repo>:environment:test",
            "repo:<owner>/<repo>:environment:prod",
            "Contributor",
            "Role Based Access Control Administrator",
            "/subscriptions/<subscription-id>",
            "AZURE_CLIENT_ID",
            "AZURE_TENANT_ID",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_PRINCIPAL_OBJECT_ID",
            "No client secret or `AZURE_CREDENTIALS`",
            "mlops-private",
            "--query \"[?scope=='$SUBSCRIPTION_SCOPE' && "
            "(roleDefinitionName=='Contributor' || "
            "roleDefinitionName=='Role Based Access Control Administrator')]",
            "intentionally omits `--include-inherited false`",
            "Azure CLI",
        ):
            self.assertIn(required, readme)

    def test_readme_documents_arc_private_runner_contract(self):
        readme = (PATTERN_ROOT / "README.md").read_text()
        for required in (
            "dedicated private Azure Kubernetes Service",
            "Actions Runner Controller (ARC)",
            "must not attempt to create, upgrade, repair, or",
            "delete the runner infrastructure",
            "mlops-private",
            "bidirectional routing",
            "privatelink.api.azureml.ms",
            "privatelink.notebooks.azure.net",
            "privatelink.blob",
            "privatelink.file",
            "privatelink.queue",
            "privatelink.table",
            "privatelink.vaultcore.azure.net",
            "privatelink.azurecr.io",
            "no public inbound management path",
            "dedicated GitHub App",
            "https://github.com/settings/apps/new",
            "loopback-only redirect URL",
            "unguessable `state`",
            "administration: write",
            "hook_attributes.active: false",
            "POST /settings/apps/{code}/conversions",
            "one-hour validity window",
            "without logging the response",
            "permissions `0600`",
            "Do not substitute a PAT",
            "GitHub PAT",
            "GitHub App client secret",
            "environment-scoped OIDC contract",
            "minRunners: 0",
            "maxRunners",
            "startup latency",
            "runner_hub_vnet_resource_id",
            "manage_runner_hub_to_workload_peering",
            "Network Contributor",
            "privatelink.dfs",
            "canonical deterministic peering name",
            "Empty/false defaults",
            "cancel remaining queued jobs",
            "delete the dedicated AKS",
            "generic placeholders",
        ):
            self.assertIn(required, readme)

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
        self.assertIn("groupId: 'dfs'", main)
        self.assertIn("privatelink.dfs.", dns)
        self.assertIn("dnsZones!.outputs.amlDnsZoneId", main)
        self.assertIn("dnsZones!.outputs.notebookDnsZoneId", main)
        self.assertIn("dnsZones!.outputs.dfsDnsZoneId", main)
        self.assertIn("runnerHubVnetResourceId", main)
        self.assertIn("manageRunnerHubToWorkloadPeering", main)
        self.assertIn("runnerHubReciprocalPeeringCommand", main)
        self.assertIn("registrationEnabled: false", dns)


if __name__ == "__main__":
    unittest.main()
