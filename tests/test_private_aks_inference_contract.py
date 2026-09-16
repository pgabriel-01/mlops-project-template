import json
import os
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


class PrivateAksInferenceContractTests(unittest.TestCase):
    def test_disabled_defaults_are_safe_and_rendered(self):
        config_path = PATTERN_ROOT / "config-infra-dev.yml"
        config = load_config(config_path)
        self.assertFalse(config["enable_private_aks_inference"])
        self.assertEqual("", config["aks_cluster_resource_id"])
        self.assertEqual("", config["aks_node_subnet_resource_id"])
        self.assertEqual("aks-inference", config["online_compute"])
        self.assertEqual("taxi-inference", config["online_environment_name"])
        self.assertEqual("1", config["online_environment_version"])
        self.assertEqual("cpu-small", config["online_instance_type"])

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
            self.assertFalse(parameters["enablePrivateAksInference"]["value"])
            self.assertEqual(
                "aks-inference",
                parameters["onlineComputeName"]["value"],
            )
            self.assertEqual(
                "cpu-small",
                parameters["onlineInstanceTypeName"]["value"],
            )
            self.assertEqual(
                "",
                parameters["onlineEnvironmentImage"]["value"],
            )
            self.assertEqual(
                "",
                parameters["aksNodeSubnetResourceId"]["value"],
            )

    def test_enabled_mode_requires_private_secure_contract(self):
        config_path = PATTERN_ROOT / "config-infra-dev.yml"
        base = load_config(config_path)
        valid = {
            **base,
            "enable_private_aks_inference": True,
            "aks_cluster_resource_id": (
                "/subscriptions/subscription-id/resourceGroups/aks-rg/providers/"
                "Microsoft.ContainerService/managedClusters/private-aks"
            ),
            "aks_node_subnet_resource_id": (
                "/subscriptions/subscription-id/resourceGroups/network-rg/providers/"
                "Microsoft.Network/virtualNetworks/hub/subnets/aks-nodes"
            ),
            "runner_hub_vnet_resource_id": (
                "/subscriptions/subscription-id/resourceGroups/network-rg/providers/"
                "Microsoft.Network/virtualNetworks/runner-hub"
            ),
            "aml_kubernetes_extension_ssl_cname": "scoring.internal.example",
            "online_environment_image": (
                "private.azurecr.io/mlops/online-runtime@sha256:"
                "0123456789abcdef0123456789abcdef0123456789abcdef"
                "0123456789abcdef"
            ),
        }
        self.assertEqual([], validate_config_values(config_path, valid))

        cases = {
            "public network": {"private_network": False},
            "missing cluster": {"aks_cluster_resource_id": ""},
            "missing node subnet": {"aks_node_subnet_resource_id": ""},
            "missing runner hub": {"runner_hub_vnet_resource_id": ""},
            "mutable environment image": {
                "online_environment_image": (
                    "private.azurecr.io/mlops/online-runtime:latest"
                )
            },
            "missing tls cname": {"aml_kubernetes_extension_ssl_cname": ""},
            "preview train": {
                "aml_kubernetes_extension_release_train": "preview"
            },
            "undersized production pool": {"online_node_min_count": 2},
            "invalid scale bounds": {
                "online_node_min_count": 4,
                "online_node_max_count": 3,
            },
            "unsupported service account": {
                "online_service_account": "custom"
            },
        }
        for name, override in cases.items():
            with self.subTest(name=name):
                self.assertTrue(
                    validate_config_values(
                        config_path,
                        {**valid, **override},
                    )
                )

    def test_bicep_contract_is_isolated_and_keyless(self):
        main = (ROOT / "infrastructure" / "bicep" / "main.bicep").read_text()
        cluster = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aks_aml_inference.bicep"
        ).read_text()
        identity = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aml_kubernetes_identity.bicep"
        ).read_text()
        compute = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aml_kubernetes_compute.bicep"
        ).read_text()
        environment = (
            ROOT
            / "infrastructure"
            / "bicep"
            / "modules"
            / "aml_environment.bicep"
        ).read_text()

        self.assertIn("enablePrivateAksInference", main)
        self.assertIn("mode: 'User'", cluster)
        self.assertIn("enableAutoScaling: true", cluster)
        self.assertIn("vnetSubnetID: nodeSubnetResourceId", cluster)
        self.assertIn("ml.azure.com/amlarc=true:NoSchedule", cluster)
        self.assertIn("ml.azure.com/inference", cluster)
        self.assertIn("trustedAccessRoleBindings@2025-07-01", cluster)
        self.assertIn(
            "Microsoft.MachineLearningServices/workspaces/mlworkload",
            cluster,
        )
        self.assertIn("internalLoadBalancerProvider: 'azure'", cluster)
        self.assertIn("allowInsecureConnections: 'False'", cluster)
        self.assertIn("configurationProtectedSettings", cluster)
        self.assertIn("sslCertPemFile: extensionTlsCertPem", cluster)
        self.assertIn("sslKeyPemFile: extensionTlsKeyPem", cluster)
        self.assertNotIn("sslSecret:", cluster)
        self.assertIn("deploymentScripts@2023-08-01", cluster)
        self.assertIn("az aks command invoke", cluster)
        self.assertIn("kubectl apply -f -", cluster)
        self.assertIn("for attempt in $(seq 1 12)", cluster)
        self.assertIn("namespaceBootstrap", cluster)
        self.assertIn("releaseTrain: extensionReleaseTrain", cluster)
        self.assertIn("federatedIdentityCredentials@2024-11-30", identity)
        self.assertIn("storageBlobDataReaderRoleId", identity)
        self.assertIn("computeType: 'Kubernetes'", compute)
        self.assertIn("identityId", compute)
        self.assertIn("workspaces/environments/versions@2025-06-01", environment)
        self.assertIn("image: imageUri", environment)
        self.assertNotIn("build:", environment)
        self.assertNotIn("condaFile:", environment)
        self.assertNotIn("listKeys(", main + cluster + identity + compute)
        self.assertNotIn("enableNodePublicIP: true", cluster)
        self.assertIn("clusterResourceId: aksClusterResourceId", main)

    def test_runtime_and_workflow_are_digest_pinned(self):
        runtime_root = PATTERN_ROOT / "mlops" / "online-runtime"
        dockerfile = (runtime_root / "Dockerfile").read_text()
        requirements = (runtime_root / "requirements.txt").read_text()
        publish = (
            PATTERN_ROOT
            / "mlops"
            / "github-actions"
            / "publish-online-runtime.yml"
        ).read_text()
        deploy = (
            PATTERN_ROOT
            / "mlops"
            / "github-actions"
            / "deploy-infrastructure.yml"
        ).read_text()

        self.assertIn("python:3.10.21-slim-bookworm@sha256:", dockerfile)
        self.assertIn("mlflow==3.13.0", requirements)
        self.assertIn("scikit-learn==1.5.2", requirements)
        self.assertIn("cloudpickle==3.1.2", requirements)
        self.assertIn("runs-on: ${{ needs.config.outputs.runner }}", publish)
        self.assertIn("docker build --pull=false", publish)
        self.assertIn("az acr login", publish)
        self.assertIn("@$digest", publish)
        self.assertIn(
            "AML_KUBERNETES_EXTENSION_TLS_CERT_PEM",
            deploy,
        )
        self.assertIn(
            "AML_KUBERNETES_EXTENSION_TLS_KEY_PEM",
            deploy,
        )
        self.assertIn(
            'amlKubernetesExtensionTlsCertPem="$TLS_CERT_PEM"',
            deploy,
        )


if __name__ == "__main__":
    unittest.main()
