import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
SCRIPT_ROOT = PATTERN_ROOT / "mlops" / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from project_config import load_config
from validate_project import validate_config_values


class ProjectContractTests(unittest.TestCase):
    def test_generated_tree_and_workflow_contract(self):
        subprocess.run(
            [sys.executable, SCRIPT_ROOT / "validate_project.py"],
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
        script = SCRIPT_ROOT / "render_bicep_parameters.py"
        base_config = (PATTERN_ROOT / "config-infra-dev.yml").read_text()
        runner_hub_id = (
            "/subscriptions/subscription-id/"
            "resourceGroups/runner-network/providers/Microsoft.Network/"
            "virtualNetworks/runner-hub"
        )
        shared_blob_zone_id = (
            "/subscriptions/subscription-id/"
            "resourceGroups/shared-dns/providers/Microsoft.Network/"
            "privateDnsZones/privatelink.blob.core.windows.net"
        )
        shared_zone_ids = {
            "privatelink.blob.core.windows.net": shared_blob_zone_id,
        }
        cases = (
            (base_config, "", False, {}),
            (
                base_config.replace(
                    'runner_hub_vnet_resource_id: ""',
                    f'runner_hub_vnet_resource_id: "{runner_hub_id}"',
                ).replace(
                    "manage_runner_hub_to_workload_peering: false",
                    "manage_runner_hub_to_workload_peering: true",
                ).replace(
                    'shared_private_dns_zone_resource_ids: "{}"',
                    "shared_private_dns_zone_resource_ids: "
                    + json.dumps(json.dumps(shared_zone_ids)),
                ),
                runner_hub_id,
                True,
                shared_zone_ids,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            for index, (
                config_text,
                expected_id,
                expected_manage,
                expected_zones,
            ) in enumerate(cases):
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
                    expected_zones,
                    parameters["sharedPrivateDnsZoneResourceIds"]["value"],
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

        shared_zone_id = (
            "/subscriptions/subscription-id/"
            "resourceGroups/shared-dns/providers/Microsoft.Network/"
            "privateDnsZones/privatelink.blob.core.windows.net"
        )
        missing_hub_for_dns = dict(config)
        missing_hub_for_dns["shared_private_dns_zone_resource_ids"] = (
            json.dumps({"privatelink.blob.core.windows.net": shared_zone_id})
        )
        self.assertTrue(validate_config_values(path, missing_hub_for_dns))

        invalid_zone_mapping = dict(config)
        invalid_zone_mapping["runner_hub_vnet_resource_id"] = runner_hub_id
        invalid_zone_mapping["shared_private_dns_zone_resource_ids"] = (
            json.dumps({"privatelink.blob.core.windows.net": shared_zone_id + "-wrong"})
        )
        self.assertTrue(validate_config_values(path, invalid_zone_mapping))

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

    def test_workflows_use_generated_project_paths(self):
        workflow_root = PATTERN_ROOT / "mlops" / "github-actions"
        infrastructure = (
            workflow_root / "deploy-infrastructure.yml"
        ).read_text()
        training = (workflow_root / "train-register-model.yml").read_text()
        online = (workflow_root / "deploy-online-endpoint.yml").read_text()
        batch = (workflow_root / "deploy-batch-endpoint.yml").read_text()

        self.assertIn("mlops/scripts/export_config.py", infrastructure)
        self.assertIn("mlops/scripts/render_bicep_parameters.py", infrastructure)
        self.assertIn("infrastructure/main.bicep", infrastructure)
        self.assertNotIn("infrastructure/bicep/", infrastructure)
        self.assertIn("job_file: mlops/azureml/train/job.yml", training)
        self.assertIn("request_file: data/taxi-request.json", online)
        self.assertIn("request_batch_file: data/taxi-batch.csv", batch)

        for content in (training, online, batch):
            self.assertIn("mlops/scripts/export_config.py", content)
            self.assertNotIn("classical/python-sdk-v2/", content)

    def test_documented_sparse_checkout_produces_runnable_tree(self):
        template_repository = "pgabriel-01/mlops-templates"
        template_ref = "be9755ccfc320fd1f2c1fb4f6b092d745d4fa6b5"

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "generated"
            selected = project / "classical" / "python-sdk-v2"
            shutil.copytree(PATTERN_ROOT, selected)
            shutil.copytree(
                ROOT / "infrastructure" / "bicep",
                project / "infrastructure" / "bicep",
            )
            shutil.copytree(
                ROOT / ".github" / "workflows",
                project / ".github" / "workflows",
            )
            shutil.copy2(ROOT / "README.md", project / "README.md")

            for name in ("data-science", "mlops", "data"):
                shutil.move(selected / name, project / name)
            shutil.move(
                selected / "runner-bootstrap",
                project / "runner-bootstrap",
            )
            for config in selected.glob("config-infra-*.yml"):
                shutil.move(config, project / config.name)

            bicep = project / "infrastructure" / "bicep"
            generated_infrastructure = project / "generated-infrastructure"
            shutil.move(bicep, generated_infrastructure)
            shutil.rmtree(project / "infrastructure")
            shutil.move(
                generated_infrastructure,
                project / "infrastructure",
            )

            shutil.rmtree(project / "mlops" / "devops-pipelines")
            workflow_source = project / "mlops" / "github-actions"
            for workflow in workflow_source.iterdir():
                shutil.move(workflow, project / ".github" / "workflows")
            workflow_source.rmdir()

            for path in project.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                rendered = content.replace(
                    "__MLOPS_TEMPLATES_REPOSITORY__",
                    template_repository,
                ).replace("__MLOPS_TEMPLATES_REF__", template_ref)
                path.write_text(rendered, encoding="utf-8")

            validator = project / "mlops" / "scripts" / "validate_project.py"
            subprocess.run(
                [sys.executable, validator, "--require-resolved-templates"],
                cwd=project,
                check=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            infrastructure_workflow = (
                project / ".github" / "workflows" /
                "deploy-infrastructure.yml"
            ).read_text()
            self.assertIn("infrastructure/main.bicep", infrastructure_workflow)
            self.assertIn(
                "mlops/scripts/render_bicep_parameters.py",
                infrastructure_workflow,
            )
            self.assertTrue(
                project.joinpath(
                    "mlops", "azureml", "train", "job.yml"
                ).is_file()
            )
            self.assertTrue(
                project.joinpath(
                    "mlops", "scripts", "export_config.py"
                ).is_file()
            )
            self.assertTrue(
                project.joinpath(
                    "runner-bootstrap", "helm", "runner-set-values.yaml"
                ).is_file()
            )
            self.assertTrue(
                project.joinpath(
                    "runner-bootstrap", "infrastructure", "main.bicepparam"
                ).is_file()
            )

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
            "No client secret or legacy Azure credentials JSON secret",
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
            "2 x `Standard_D2ads_v6` (4 vCPUs total)",
            "`/home/runner/run.sh` explicitly",
            "shared_private_dns_zone_resource_ids",
            "24-character maximum",
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
        self.assertIn("isolationMode: 'AllowInternetOutbound'", workspace)
        self.assertNotIn("serverlessComputeSettings:", workspace)
        self.assertNotIn("serverlessComputeCustomSubnet", workspace)
        self.assertIn(
            "publicNetworkAccess: enableNetworkIsolation ? 'Disabled' : 'Enabled'",
            workspace,
        )
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
        self.assertIn("registrationEnabled: false", (
            ROOT
            / "infrastructure/bicep/modules/private_dns_zone_vnet_link.bicep"
        ).read_text())

    def test_workspace_does_not_mix_managed_and_custom_vnet_modes(self):
        workspace = (
            ROOT / "infrastructure/bicep/modules/aml_workspace.bicep"
        ).read_text()
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()

        managed_vnet_properties = (
            "managedNetwork:",
            "isolationMode:",
        )
        custom_vnet_properties = (
            "serverlessComputeSettings:",
            "serverlessComputeCustomSubnet",
        )

        for property_name in managed_vnet_properties:
            self.assertIn(property_name, workspace)
        self.assertFalse(
            any(property_name in workspace for property_name in custom_vnet_properties)
        )
        self.assertNotIn("param computeSubnetId", workspace)
        self.assertNotIn("computeSubnetId:", main)
        self.assertIn(
            "subnetId: enableVNet ? vnet!.outputs.computeSubnetId : ''",
            main,
        )

    def test_key_vault_name_stays_within_exact_azure_boundary(self):
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()
        key_vault = (
            ROOT / "infrastructure/bicep/modules/key_vault.bicep"
        ).read_text()

        self.assertIn(
            "var keyVaultPrefix = take(replace(toLower(prefix), '-', ''), 5)",
            main,
        )
        self.assertIn("uniqueString(rg.id)", main)
        self.assertIn("keyVaultName: keyVaultName", main)
        self.assertIn("name: keyVaultName", key_vault)
        self.assertNotIn("name: 'kv-${baseName}'", key_vault)

        first = "kv-" + "retai" + "a" * 13 + "dev"
        second = "kv-" + "retai" + "b" * 13 + "dev"
        self.assertEqual(len(first), 24)
        self.assertEqual(len(second), 24)
        self.assertNotEqual(first, second)

    def test_shared_runner_hub_dns_zones_are_reused_explicitly(self):
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()
        dns = (
            ROOT / "infrastructure/bicep/modules/private_dns_zones.bicep"
        ).read_text()
        link = (
            ROOT
            / "infrastructure/bicep/modules/private_dns_zone_vnet_link.bicep"
        ).read_text()

        self.assertIn("param sharedPrivateDnsZoneResourceIds object = {}", main)
        self.assertIn(
            "sharedPrivateDnsZoneResourceIds: sharedPrivateDnsZoneResourceIds",
            main,
        )
        self.assertIn("contains(sharedPrivateDnsZoneResourceIds, zone)", dns)
        self.assertIn("for zoneId in privateDnsZoneIds", dns)
        self.assertIn("for zone in managedDnsZones", dns)
        self.assertIn("output blobDnsZoneId string = privateDnsZoneIds[0]", dns)
        self.assertIn("resource privateDnsZone", link)
        self.assertIn("existing = {", link)


if __name__ == "__main__":
    unittest.main()
