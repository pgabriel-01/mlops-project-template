import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
SCRIPT_ROOT = PATTERN_ROOT / "mlops" / "scripts"
ONLINE_SCRIPT = PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "deploy.py"
LOCK_SCRIPT = (
    PATTERN_ROOT / "mlops" / "azureml" / "deploy" / "online" / "deployment_lock.py"
)
BASTION_PREFLIGHT = SCRIPT_ROOT / "check_legacy_bastion.py"
sys.path.insert(0, str(SCRIPT_ROOT))

from project_config import load_config
from validate_project import validate_config_values

SPEC = importlib.util.spec_from_file_location("managed_online_deploy", ONLINE_SCRIPT)
assert SPEC and SPEC.loader
managed_online_deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(managed_online_deploy)
BASTION_SPEC = importlib.util.spec_from_file_location(
    "check_legacy_bastion", BASTION_PREFLIGHT
)
assert BASTION_SPEC and BASTION_SPEC.loader
check_legacy_bastion = importlib.util.module_from_spec(BASTION_SPEC)
BASTION_SPEC.loader.exec_module(check_legacy_bastion)
LOCK_SPEC = importlib.util.spec_from_file_location("deployment_lock", LOCK_SCRIPT)
assert LOCK_SPEC and LOCK_SPEC.loader
deployment_lock = importlib.util.module_from_spec(LOCK_SPEC)
LOCK_SPEC.loader.exec_module(deployment_lock)


class ManagedOnlineEndpointContractTests(unittest.TestCase):
    def test_environment_defaults_are_private_and_deterministic(self):
        for environment, expected_count, jumpbox_enabled in (
            ("dev", 1, True),
            ("test", 3, False),
            ("prod", 3, False),
        ):
            path = PATTERN_ROOT / f"config-infra-{environment}.yml"
            config = load_config(path)
            self.assertTrue(config["enable_managed_online_endpoint"])
            self.assertEqual("managed-online", config["online_endpoint_suffix"])
            self.assertEqual("blue", config["online_deployment_name"])
            self.assertEqual("green", config["online_alternate_deployment_name"])
            self.assertEqual(100, config["online_traffic_percentage"])
            self.assertEqual(
                "deployment-locks",
                config["online_lock_container_name"],
            )
            self.assertEqual(
                "mlops/azureml/deploy/online/code",
                config["online_code_directory"],
            )
            self.assertEqual("score.py", config["online_scoring_script"])
            self.assertEqual("Standard_DS3_v2", config["online_instance_type"])
            self.assertEqual(expected_count, config["online_instance_count"])
            self.assertTrue(config["online_mlflow_no_code"])
            self.assertEqual("", config["online_environment_name"])
            self.assertEqual("", config["online_environment_version"])
            self.assertEqual("", config["online_environment_image"])
            self.assertEqual(jumpbox_enabled, config["enable_dev_jumpbox"])
            self.assertNotEqual(
                "latest",
                config["dev_jumpbox_ubuntu_image_version"],
            )
            self.assertEqual(
                "2.44.1",
                config["dev_jumpbox_azure_ml_extension_version"],
            )
            self.assertIn(
                (
                    config["location"],
                    config["dev_jumpbox_ubuntu_image_version"],
                ),
                {
                    ("eastus", "24.04.202608270"),
                    ("eastus2", "24.04.202608270"),
                },
            )
            self.assertEqual([], validate_config_values(path, config))

    def test_bicep_parameters_render_managed_endpoint_and_jumpbox(self):
        config_path = PATTERN_ROOT / "config-infra-dev.yml"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "parameters.json"
            subprocess.run(
                [
                    sys.executable,
                    SCRIPT_ROOT / "render_bicep_parameters.py",
                    config_path,
                    output,
                ],
                check=True,
                env={
                    **os.environ,
                    "AZURE_PRINCIPAL_OBJECT_ID": (
                        "00000000-0000-0000-0000-000000000001"
                    ),
                },
            )
            parameters = json.loads(output.read_text())["parameters"]
            self.assertTrue(parameters["enableManagedOnlineEndpoint"]["value"])
            self.assertTrue(parameters["enableDevJumpbox"]["value"])
            self.assertNotIn("devJumpboxBootstrapSshPublicKey", parameters)
            self.assertEqual(
                "24.04.202608270",
                parameters["devJumpboxUbuntuImageVersion"]["value"],
            )
            self.assertEqual(
                "2.44.1",
                parameters["devJumpboxAzureMlExtensionVersion"]["value"],
            )
            for removed in (
                "enablePrivateAksInference",
                "aksClusterResourceId",
                "amlKubernetesExtensionSslCname",
            ):
                self.assertNotIn(removed, parameters)

    def test_workspace_contract_uses_managed_network_v1(self):
        workspace = (
            ROOT / "infrastructure" / "bicep" / "modules" / "aml_workspace.bicep"
        ).read_text()
        network_approvers = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aml_network_approvers.bicep"
        ).read_text()
        main = (ROOT / "infrastructure" / "bicep" / "main.bicep").read_text()
        identity = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aml_online_endpoint_identity.bicep"
        ).read_text()
        storage = (
            ROOT / "infrastructure" / "bicep" / "modules" / "storage_account.bicep"
        ).read_text()

        self.assertIn("v1LegacyMode: false", workspace)
        self.assertIn("isolationMode: 'AllowOnlyApprovedOutbound'", workspace)
        self.assertIn("managedNetworkKind: 'V1'", workspace)
        self.assertNotIn("workspaces/outboundRules", main + workspace)
        self.assertIn(
            "Azure AI Enterprise Network Connection Approver",
            network_approvers,
        )
        self.assertIn("scope: workspace", network_approvers)
        self.assertIn("acdd72a7-3385-48ef-bd42-f606fba81ae7", network_approvers)
        self.assertNotIn("Contributor", network_approvers)
        self.assertNotIn("Owner", network_approvers)
        self.assertIn("Storage Blob Data Reader", identity)
        self.assertIn("AcrPull", identity)
        self.assertIn("f1a07417-d97a-45cb-824c-7a7467783830", identity)
        self.assertIn("scope: endpointIdentity", identity)
        self.assertNotIn("Contributor", identity)
        self.assertNotIn("Kubernetes", main + identity)
        self.assertIn("name: 'deployment-locks'", storage)
        self.assertIn("scope: deploymentLocks", storage)
        self.assertIn("allowSharedKeyAccess: false", storage)
        self.assertIn("minimumTlsVersion: 'TLS1_2'", storage)

    def test_jumpbox_contract_is_private_and_entra_only(self):
        main = (ROOT / "infrastructure" / "bicep" / "main.bicep").read_text()
        vnet = (
            ROOT / "infrastructure" / "bicep" / "modules" / "vnet.bicep"
        ).read_text()
        jumpbox = (
            ROOT / "infrastructure" / "bicep" / "modules" / "bastion.bicep"
        ).read_text()
        bootstrap_key = (
            ROOT / "infrastructure" / "bicep" / "assets" / "dev-jumpbox-bootstrap.pub"
        ).read_text()

        self.assertIn("param enableDevJumpbox bool = env == 'dev'", main)
        self.assertIn("name: 'administration'", vnet)
        self.assertIn("name: 'Premium'", jumpbox)
        self.assertIn("name: 'bastion-private-${baseName}'", jumpbox)
        self.assertIn("enablePrivateOnlyBastion: true", jumpbox)
        self.assertNotIn("publicIPAddresses", jumpbox)
        self.assertIn("disablePasswordAuthentication: true", jumpbox)
        self.assertIn("bootstrapSshPublicKey", jumpbox)
        self.assertIn(
            "trim(loadTextContent('../assets/dev-jumpbox-bootstrap.pub'))",
            jumpbox,
        )
        self.assertTrue(bootstrap_key.startswith("ssh-ed25519 "))
        self.assertNotIn("PRIVATE KEY", bootstrap_key)
        self.assertIn("rm -f /home/{4}/.ssh/authorized_keys", jumpbox)
        self.assertNotIn("adminPassword", jumpbox)
        self.assertIn("type: 'SystemAssigned'", jumpbox)
        self.assertIn("AADSSHLoginForLinux", jumpbox)
        self.assertIn("autoUpgradeMinorVersion: true", jumpbox)
        self.assertNotIn("enableAutomaticUpgrade", jumpbox)
        self.assertIn("securityType: 'TrustedLaunch'", jumpbox)
        self.assertIn("scope: jumpboxVm", jumpbox)
        self.assertIn("scope: jumpboxNic", jumpbox)
        self.assertIn("scope: bastion", jumpbox)
        self.assertIn(
            "AZURE_EXTENSION_DIR=/opt/az-extensions az extension add "
            "--name ml --version {1} --yes",
            jumpbox,
        )
        self.assertIn("Microsoft.DevTestLab/schedules@2018-09-15", jumpbox)
        self.assertIn("DisplayName: 'Dev jumpbox'", jumpbox)
        self.assertIn("Virtual Machine User Login", jumpbox)
        self.assertIn("resource jumpboxVmReader", jumpbox)
        self.assertIn("scope: jumpboxVm", jumpbox)
        self.assertIn("resource jumpboxNicReader", jumpbox)
        self.assertIn("scope: jumpboxNic", jumpbox)
        self.assertIn("resource bastionReader", jumpbox)
        self.assertIn("scope: bastion", jumpbox)
        self.assertIn("acdd72a7-3385-48ef-bd42-f606fba81ae7", jumpbox)
        self.assertNotIn("scope: resourceGroup", jumpbox)
        self.assertNotIn("Virtual Machine Administrator Login", jumpbox)

    def test_legacy_bastion_preflight_fails_closed(self):
        def fake_az_json(*args):
            if args[:2] == ("group", "exists"):
                return True
            if args[:3] == ("network", "bastion", "list"):
                return [
                    {
                        "name": "bastion-old",
                        "sku": {"name": "Basic"},
                        "provisioningState": "Succeeded",
                        "enableTunneling": True,
                        "ipConfigurations": [
                            {
                                "name": "AzureBastionHostIpConfiguration",
                                "privateIPAllocationMethod": "Dynamic",
                                "publicIpAddress": {
                                    "id": "/subscriptions/example/resourceGroups/"
                                    "rg-mlops-demo001dev/providers/Microsoft.Network/"
                                    "publicIPAddresses/pip-bastion-mlops-demo001dev"
                                },
                                "subnet": {
                                    "id": "/subscriptions/example/resourceGroups/"
                                    "rg-mlops-demo001dev/providers/Microsoft.Network/"
                                    "virtualNetworks/vnet-demo/subnets/"
                                    "AzureBastionSubnet"
                                },
                            }
                        ],
                    }
                ]
            return [
                {
                    "name": "pip-bastion-mlops-demo001dev",
                    "type": "Microsoft.Network/publicIPAddresses",
                },
                {
                    "name": "vm-jumpbox-mlops-demo001dev",
                    "type": "Microsoft.Compute/virtualMachines",
                },
                {
                    "name": "nic-jumpbox-mlops-demo001dev",
                    "type": "Microsoft.Network/networkInterfaces",
                },
                {
                    "name": "nsg-jumpbox-mlops-demo001dev",
                    "type": "Microsoft.Network/networkSecurityGroups",
                },
            ]

        with patch.object(check_legacy_bastion, "az_json", side_effect=fake_az_json):
            blockers = check_legacy_bastion.find_blockers(
                "rg-mlops-demo001dev", "mlops-demo001dev"
            )
        self.assertIn("Bastion bastion-old", blockers)
        self.assertIn(
            "Microsoft.Network/publicIPAddresses " "pip-bastion-mlops-demo001dev",
            blockers,
        )
        self.assertIn(
            "Microsoft.Compute/virtualMachines vm-jumpbox-mlops-demo001dev",
            blockers,
        )
        self.assertIn(
            "Microsoft.Network/networkInterfaces nic-jumpbox-mlops-demo001dev",
            blockers,
        )
        self.assertIn(
            "Microsoft.Network/networkSecurityGroups nsg-jumpbox-mlops-demo001dev",
            blockers,
        )

    def test_existing_desired_private_bastion_passes_preflight(self):
        def fake_az_json(*args):
            if args[:2] == ("group", "exists"):
                return True
            if args[:3] == ("network", "bastion", "list"):
                return [
                    {
                        "name": "bastion-private-mlops-demo001dev",
                        "sku": {"name": "Premium"},
                        "provisioningState": "Succeeded",
                        "enablePrivateOnlyBastion": None,
                        "enableTunneling": True,
                        "ipConfigurations": [
                            {
                                "name": "private",
                                "privateIPAllocationMethod": "Dynamic",
                                "provisioningState": "Succeeded",
                                "subnet": {
                                    "id": "/subscriptions/example/resourceGroups/"
                                    "rg-mlops-demo001dev/providers/Microsoft.Network/"
                                    "virtualNetworks/vnet-demo/subnets/"
                                    "AzureBastionSubnet"
                                },
                            }
                        ],
                    }
                ]
            return []

        with patch.object(check_legacy_bastion, "az_json", side_effect=fake_az_json):
            blockers = check_legacy_bastion.find_blockers(
                "rg-mlops-demo001dev", "mlops-demo001dev"
            )
        self.assertEqual([], blockers)

    def test_expected_bastion_with_public_ip_fails_preflight(self):
        def fake_az_json(*args):
            if args[:2] == ("group", "exists"):
                return True
            if args[:3] == ("network", "bastion", "list"):
                return [
                    {
                        "name": "bastion-private-mlops-demo001dev",
                        "sku": {"name": "Premium"},
                        "provisioningState": "Succeeded",
                        "enableTunneling": True,
                        "ipConfigurations": [
                            {
                                "name": "private",
                                "privateIPAllocationMethod": "Dynamic",
                                "publicIpAddress": {"id": "/public-ip"},
                                "subnet": {
                                    "id": "/subscriptions/example/resourceGroups/"
                                    "rg-mlops-demo001dev/providers/Microsoft.Network/"
                                    "virtualNetworks/vnet-demo/subnets/"
                                    "AzureBastionSubnet"
                                },
                            }
                        ],
                    }
                ]
            return []

        with patch.object(check_legacy_bastion, "az_json", side_effect=fake_az_json):
            blockers = check_legacy_bastion.find_blockers(
                "rg-mlops-demo001dev", "mlops-demo001dev"
            )
        self.assertEqual(
            ["Bastion bastion-private-mlops-demo001dev"],
            blockers,
        )

    def test_only_exact_private_bastion_posture_is_idempotent(self):
        expected_name = "bastion-private-mlops-demo001dev"
        desired = {
            "name": expected_name,
            "sku": {"name": "Premium"},
            "provisioningState": "Succeeded",
            "enableTunneling": True,
            "ipConfigurations": [
                {
                    "name": "private",
                    "privateIPAllocationMethod": "Dynamic",
                    "provisioningState": "Succeeded",
                    "subnet": {
                        "id": "/subscriptions/example/resourceGroups/"
                        "rg-mlops-demo001dev/providers/Microsoft.Network/"
                        "virtualNetworks/vnet-demo/subnets/AzureBastionSubnet"
                    },
                }
            ],
        }
        self.assertTrue(
            check_legacy_bastion.is_desired_private_bastion(desired, expected_name)
        )

        invalid_variants = []
        for path, value in (
            (("name",), "bastion-old"),
            (("sku", "name"), "Standard"),
            (("provisioningState",), "Failed"),
            (("enablePrivateOnlyBastion",), False),
            (("enableTunneling",), False),
            (("ipConfigurations", 0, "name"), "default"),
            (("ipConfigurations", 0, "privateIPAllocationMethod"), "Static"),
            (("ipConfigurations", 0, "provisioningState"), "Updating"),
            (("ipConfigurations", 0, "subnet", "id"), "/wrong-subnet"),
            (("ipConfigurations", 0, "publicIpAddress"), {"id": "/public-ip"}),
        ):
            variant = json.loads(json.dumps(desired))
            target = variant
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            invalid_variants.append(variant)
        invalid_variants.extend(
            [
                {**desired, "ipConfigurations": []},
                {
                    **desired,
                    "ipConfigurations": desired["ipConfigurations"] * 2,
                },
            ]
        )
        for variant in invalid_variants:
            with self.subTest(variant=variant):
                self.assertFalse(
                    check_legacy_bastion.is_desired_private_bastion(
                        variant, expected_name
                    )
                )

    def test_online_workflow_has_no_kubernetes_or_tls_contract(self):
        workflow = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-online-endpoint.yml"
        ).read_text()
        ado_pipeline = (
            PATTERN_ROOT
            / "mlops"
            / "devops-pipelines"
            / "deploy-online-endpoint-pipeline.yml"
        ).read_text()
        infrastructure = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-infrastructure.yml"
        ).read_text()
        deploy = ONLINE_SCRIPT.read_text()
        lock = LOCK_SCRIPT.read_text()

        self.assertIn("id-token: write", workflow)
        self.assertIn("az ml workspace provision-network", workflow)
        self.assertIn("az ml workspace provision-network", ado_pipeline)
        self.assertNotIn("--include-spark", workflow)
        self.assertNotIn("--include-spark", ado_pipeline)
        self.assertIn("mlops/azureml/deploy/online/deploy.py", workflow)
        self.assertIn("check_legacy_bastion.py", infrastructure)
        self.assertIn("az vm image show", infrastructure)
        self.assertNotIn("ssh-keygen", infrastructure)
        self.assertIn('auth_mode="aad_token"', deploy)
        self.assertIn('public_network_access="disabled"', deploy)
        self.assertIn("begin_create_or_update(deployment).result()", deploy)
        self.assertIn("name=candidate_name", deploy)
        self.assertIn("deployment_name=candidate_name", deploy)
        self.assertIn("promoted_traffic(", deploy)
        self.assertIn("CodeConfiguration(", deploy)
        self.assertIn("with endpoint_deployment_lock(", deploy)
        self.assertIn("lease.ensure_held()", deploy)
        self.assertIn('blob_name=f"{endpoint_name}.lock"', lock)
        self.assertIn("LEASE_DURATION_SECONDS = 60", lock)
        self.assertIn("LEASE_RENEWAL_SECONDS = 20", lock)
        self.assertIn("Another deployment holds the Azure lease", lock)
        self.assertLess(
            deploy.index("begin_create_or_update(deployment).result()"),
            deploy.index("client.online_endpoints.invoke("),
        )
        self.assertLess(
            deploy.index("client.online_endpoints.invoke("),
            deploy.index("live_endpoint.traffic = promoted_traffic("),
        )
        for retired in (
            "tls_ca_key_vault_secret_id",
            "AML_KUBERNETES",
            "completePrivateAksInferenceDeployment",
            "azureml-inference-namespace",
            "KubernetesOnlineEndpoint",
            "KubernetesOnlineDeployment",
        ):
            self.assertNotIn(retired, workflow + infrastructure + deploy)

    def test_workspace_validation_rejects_legacy_or_public_configuration(self):
        valid = SimpleNamespace(
            public_network_access="Disabled",
            v1_legacy_mode=False,
            managed_network=SimpleNamespace(isolation_mode="AllowOnlyApprovedOutbound"),
        )
        managed_online_deploy.validate_workspace(valid)

        for override in (
            {"public_network_access": "Enabled"},
            {"v1_legacy_mode": True},
            {
                "managed_network": SimpleNamespace(
                    isolation_mode="AllowInternetOutbound"
                )
            },
        ):
            workspace = SimpleNamespace(**{**valid.__dict__, **override})
            with self.subTest(override=override):
                with self.assertRaises(RuntimeError):
                    managed_online_deploy.validate_workspace(workspace)

    def test_image_mode_requires_complete_immutable_environment(self):
        request = PATTERN_ROOT / "data" / "taxi-request.json"
        base = {
            "mlflow_no_code": False,
            "environment_name": "taxi-inference",
            "environment_version": "1",
            "environment_image": (
                "registry.azurecr.io/online@sha256:"
                "0123456789abcdef0123456789abcdef0123456789abcdef"
                "0123456789abcdef"
            ),
            "code_directory": ONLINE_SCRIPT.parent / "code",
            "scoring_script": "score.py",
            "deployment_name": "blue",
            "alternate_deployment_name": "green",
            "traffic_percentage": 100,
            "lock_storage_account_name": "stmlopsdev",
            "lock_container_name": "deployment-locks",
            "instance_count": 1,
            "request_file": request,
        }
        managed_online_deploy.validate_environment_args(Namespace(**base))
        for key in (
            "environment_name",
            "environment_version",
            "environment_image",
        ):
            with self.subTest(key=key):
                invalid = {**base, key: ""}
                with self.assertRaises(ValueError):
                    managed_online_deploy.validate_environment_args(
                        Namespace(**invalid)
                    )

    def test_blue_green_candidate_preserves_serving_deployment(self):
        candidate = managed_online_deploy.select_candidate_deployment(
            deployment_fingerprints={"blue": "old", "green": "older"},
            traffic={"blue": 100},
            primary_name="blue",
            alternate_name="green",
            desired_fingerprint="new",
        )
        self.assertEqual("green", candidate)

    def test_blue_green_rerun_reuses_same_candidate(self):
        candidate = managed_online_deploy.select_candidate_deployment(
            deployment_fingerprints={"blue": "old", "green": "desired"},
            traffic={"green": 100},
            primary_name="blue",
            alternate_name="green",
            desired_fingerprint="desired",
        )
        self.assertEqual("green", candidate)

    def test_same_model_changed_rollout_inputs_use_inactive_slot(self):
        base = Namespace(
            mlflow_no_code=False,
            model_name="taxi-model",
            model_version="2",
            environment_name="taxi-inference",
            environment_version="1",
            environment_image=(
                "registry.azurecr.io/online@sha256:"
                "0123456789abcdef0123456789abcdef0123456789abcdef"
                "0123456789abcdef"
            ),
            code_directory=ONLINE_SCRIPT.parent / "code",
            scoring_script="score.py",
            instance_type="Standard_DS3_v2",
            instance_count=1,
        )
        serving_fingerprint = managed_online_deploy.deployment_fingerprint(base)
        for field, value in (
            ("environment_version", "2"),
            ("instance_type", "Standard_DS4_v2"),
            ("instance_count", 2),
        ):
            changed = Namespace(**{**vars(base), field: value})
            desired_fingerprint = managed_online_deploy.deployment_fingerprint(changed)
            with self.subTest(field=field):
                self.assertNotEqual(serving_fingerprint, desired_fingerprint)
                self.assertEqual(
                    "green",
                    managed_online_deploy.select_candidate_deployment(
                        deployment_fingerprints={"blue": serving_fingerprint},
                        traffic={"blue": 100},
                        primary_name="blue",
                        alternate_name="green",
                        desired_fingerprint=desired_fingerprint,
                    ),
                )
        with tempfile.TemporaryDirectory() as directory:
            code_directory = Path(directory)
            scoring_script = code_directory / "score.py"
            scoring_script.write_text("def run(data):\n    return data\n")
            first = Namespace(
                **{
                    **vars(base),
                    "code_directory": code_directory,
                }
            )
            first_fingerprint = managed_online_deploy.deployment_fingerprint(first)
            scoring_script.write_text("def run(data):\n    return {'changed': data}\n")
            changed_fingerprint = managed_online_deploy.deployment_fingerprint(first)
            self.assertNotEqual(first_fingerprint, changed_fingerprint)
            self.assertEqual(
                "green",
                managed_online_deploy.select_candidate_deployment(
                    deployment_fingerprints={"blue": first_fingerprint},
                    traffic={"blue": 100},
                    primary_name="blue",
                    alternate_name="green",
                    desired_fingerprint=changed_fingerprint,
                ),
            )

    def test_partial_promotion_retains_previous_deployment(self):
        self.assertEqual(
            {"blue": 90, "green": 10},
            managed_online_deploy.promoted_traffic(
                current_traffic={"blue": 100},
                candidate_name="green",
                traffic_percentage=10,
            ),
        )

    def test_new_model_fails_when_both_slots_receive_traffic(self):
        with self.assertRaisesRegex(RuntimeError, "Both blue-green"):
            managed_online_deploy.select_candidate_deployment(
                deployment_fingerprints={"blue": "one", "green": "two"},
                traffic={"blue": 90, "green": 10},
                primary_name="blue",
                alternate_name="green",
                desired_fingerprint="three",
            )

    def test_image_mode_requires_code_configuration(self):
        request = PATTERN_ROOT / "data" / "taxi-request.json"
        args = Namespace(
            mlflow_no_code=False,
            environment_name="taxi-inference",
            environment_version="1",
            environment_image=(
                "registry.azurecr.io/online@sha256:"
                "0123456789abcdef0123456789abcdef0123456789abcdef"
                "0123456789abcdef"
            ),
            code_directory=None,
            scoring_script="",
            deployment_name="blue",
            alternate_deployment_name="green",
            traffic_percentage=100,
            lock_storage_account_name="stmlopsdev",
            lock_container_name="deployment-locks",
            instance_count=1,
            request_file=request,
        )
        with self.assertRaisesRegex(ValueError, "code directory"):
            managed_online_deploy.validate_environment_args(args)

    def test_azure_devops_online_pipeline_requires_private_pool_and_oidc(self):
        pipeline = (
            PATTERN_ROOT
            / "mlops"
            / "devops-pipelines"
            / "deploy-online-endpoint-pipeline.yml"
        ).read_text()
        self.assertIn("privateAgentPool", pipeline)
        self.assertIn("pool:\n          name:", pipeline)
        self.assertNotIn("vmImage:", pipeline)
        self.assertIn("A private self-hosted agent pool is required", pipeline)
        self.assertIn("workload identity federation", pipeline)
        self.assertIn('if [[ -z "${idToken:-}" ]]', pipeline)
        self.assertIn("--alternate-deployment-name", pipeline)
        self.assertIn("--traffic-percentage", pipeline)
        self.assertIn("--code-directory", pipeline)
        self.assertIn("--lock-storage-account-name", pipeline)
        self.assertIn("--lock-container-name", pipeline)
        self.assertIn("AzureCLI@2", pipeline)

    def test_github_and_azure_devops_share_endpoint_lock_contract(self):
        github = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-online-endpoint.yml"
        ).read_text()
        azure_devops = (
            PATTERN_ROOT
            / "mlops"
            / "devops-pipelines"
            / "deploy-online-endpoint-pipeline.yml"
        ).read_text()
        for workflow in (github, azure_devops):
            self.assertIn("--lock-storage-account-name", workflow)
            self.assertIn("--lock-container-name", workflow)
            self.assertIn("properties.storageAccount", workflow)

    def test_renewable_lock_releases_and_surfaces_renewal_loss(self):
        class FakeLeaseClient:
            def __init__(self):
                self.acquired = False
                self.released = False

            def acquire(self, lease_duration):
                self.acquired = lease_duration == 60

            def renew(self):
                return None

            def release(self):
                self.released = True

        client = FakeLeaseClient()
        lease = deployment_lock.RenewableLease(client)
        lease.acquire()
        lease.ensure_held()
        lease.release()
        self.assertTrue(client.acquired)
        self.assertTrue(client.released)

        failed_client = FakeLeaseClient()
        failed_lease = deployment_lock.RenewableLease(failed_client)
        failed_lease.acquire()
        failed_lease._renewal_error = RuntimeError("renew failed")
        with self.assertRaisesRegex(RuntimeError, "Lost the Azure deployment lock"):
            failed_lease.release()
        self.assertTrue(failed_client.released)


if __name__ == "__main__":
    unittest.main()
