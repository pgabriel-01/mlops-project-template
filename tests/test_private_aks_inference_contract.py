import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
SCRIPT_ROOT = PATTERN_ROOT / "mlops" / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from project_config import load_config
from validate_project import validate_config_values


class PrivateAksInferenceContractTests(unittest.TestCase):
    @staticmethod
    def _runtime_publish_script():
        publish = (
            PATTERN_ROOT / "mlops" / "github-actions" / "publish-online-runtime.yml"
        ).read_text()
        publish_step = publish.split("      - id: publish", 1)[1]
        script = publish_step.split("        run: |\n", 1)[1]
        return textwrap.dedent(script)

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
            "IP instead of tls FQDN": {
                "aml_kubernetes_extension_ssl_cname": "10.0.0.4"
            },
            "preview train": {"aml_kubernetes_extension_release_train": "preview"},
            "undersized production pool": {"online_node_min_count": 2},
            "invalid scale bounds": {
                "online_node_min_count": 4,
                "online_node_max_count": 3,
            },
            "unsupported service account": {"online_service_account": "custom"},
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
            ROOT / "infrastructure" / "bicep" / "modules" / "aks_aml_inference.bicep"
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
            ROOT / "infrastructure" / "bicep" / "modules" / "aml_environment.bicep"
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
            PATTERN_ROOT / "mlops" / "github-actions" / "publish-online-runtime.yml"
        ).read_text()
        runner_dockerfile = (
            PATTERN_ROOT / "runner-bootstrap" / "image" / "Dockerfile"
        ).read_text()
        runner_smoke = (
            PATTERN_ROOT / "mlops" / "github-actions" / "runner-smoke-test.yml"
        ).read_text()
        deploy = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-infrastructure.yml"
        ).read_text()

        self.assertIn("python:3.10.21-slim-bookworm@sha256:", dockerfile)
        self.assertIn("mlflow==3.13.0", requirements)
        self.assertIn("scikit-learn==1.5.2", requirements)
        self.assertIn("cloudpickle==3.1.2", requirements)
        self.assertIn("runs-on: ${{ needs.config.outputs.runner }}", publish)
        self.assertIn(
            "immutable_image: ${{ steps.publish.outputs.immutable_image }}",
            publish,
        )
        self.assertIn("IMAGE_TAG: ${{ github.sha }}", publish)
        self.assertIn("KANIKO_EXECUTOR: /kaniko/executor", publish)
        self.assertIn('"$KANIKO_EXECUTOR" version', publish)
        self.assertIn("az acr login", publish)
        self.assertIn("--expose-token", publish)
        self.assertIn('[[ -z "$token" ]]', publish)
        self.assertIn('echo "::add-mask::$token"', publish)
        self.assertIn('chmod 0700 "$auth_dir"', publish)
        self.assertIn("path.chmod(0o600)", publish)
        self.assertIn('DOCKER_CONFIG="$auth_dir" "$KANIKO_EXECUTOR"', publish)
        self.assertIn(
            '--destination "$login_server/mlops/online-runtime:$IMAGE_TAG"',
            publish,
        )
        self.assertIn('--digest-file "$digest_file"', publish)
        self.assertIn("--cleanup", publish)
        self.assertIn('rm -f "$auth_dir/config.json" "$digest_file"', publish)
        self.assertIn("az acr manifest show-metadata", publish)
        self.assertIn("^sha256:[0-9a-f]{64}$", publish)
        self.assertIn('"$digest" != "$built_digest"', publish)
        self.assertIn("@$digest", publish)
        self.assertIn(
            'echo "immutable_image=$immutable_image" >> "$GITHUB_OUTPUT"',
            publish,
        )
        for prohibited in (
            "docker login",
            "docker build",
            "docker push",
            "az acr build",
            "buildah",
            "apt-get",
            "sudo",
        ):
            self.assertNotIn(prohibited, publish)
        self.assertIn(
            "gcr.io/kaniko-project/executor@sha256:"
            "c3109d5926a997b100c4343944e06c6b30a6804b2f9abe0994d3de6ef92b028e",
            runner_dockerfile,
        )
        self.assertIn(
            "COPY --from=kaniko /kaniko/executor /kaniko/executor",
            runner_dockerfile,
        )
        self.assertIn("chown -R runner:runner /kaniko", runner_dockerfile)
        self.assertIn("/kaniko/executor version", runner_dockerfile)
        self.assertIn("test ! -S /var/run/docker.sock", runner_smoke)
        self.assertIn("/kaniko/executor version", runner_smoke)
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
        self.assertIn("openssl x509 -noout -ext subjectAltName", deploy)
        self.assertIn('openssl x509 -noout -checkhost "$SSL_CNAME"', deploy)

        documentation = (ROOT / "docs" / "private-aks-inference.md").read_text()
        self.assertIn(
            ".status.loadBalancer.ingress[0].ip",
            documentation,
        )
        self.assertIn("private DNS **A", documentation)
        self.assertIn("DNS Subject Alternative Name", documentation)
        self.assertNotIn(
            "Point the private CNAME at the internal",
            documentation,
        )

    def test_runtime_publish_script_outputs_only_verified_digest_uri(self):
        script = self._runtime_publish_script()
        digest = "sha256:" + ("a" * 64)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_az = root / "az"
            fake_az.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    case "$1 $2 $3" in
                      "ml workspace show")
                        echo "/subscriptions/test/resourceGroups/test/providers/Microsoft.ContainerRegistry/registries/private"
                        ;;
                      "acr show --name")
                        echo "private.azurecr.io"
                        ;;
                      "acr login --name")
                        echo "refresh-token"
                        ;;
                      "acr manifest show-metadata")
                        echo "$FAKE_DIGEST"
                        ;;
                      *)
                        echo "Unexpected az command: $*" >&2
                        exit 1
                        ;;
                    esac
                    """
                )
            )
            fake_az.chmod(0o755)
            fake_kaniko = root / "kaniko-executor"
            fake_kaniko.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    if [[ ${1:-} == version ]]; then
                      echo "Kaniko version v1.23.2"
                      exit 0
                    fi
                    test -f "$DOCKER_CONFIG/config.json"
                    printf '%s' "$DOCKER_CONFIG" > "$FAKE_AUTH_PATH_LOG"
                    while (($#)); do
                      if [[ $1 == --digest-file ]]; then
                        printf '%s' "$FAKE_DIGEST" > "$2"
                        exit 0
                      fi
                      shift
                    done
                    echo "Missing --digest-file" >&2
                    exit 1
                    """
                )
            )
            fake_kaniko.chmod(0o755)
            output = root / "github-output"
            summary = root / "github-summary"
            auth_path_log = root / "auth-path"
            environment = {
                **os.environ,
                "PATH": f"{root}:{os.environ['PATH']}",
                "RESOURCE_GROUP": "test-rg",
                "WORKSPACE_NAME": "test-workspace",
                "IMAGE_TAG": "1" * 40,
                "FAKE_DIGEST": digest,
                "FAKE_AUTH_PATH_LOG": str(auth_path_log),
                "KANIKO_EXECUTOR": str(fake_kaniko),
                "GITHUB_WORKSPACE": str(root),
                "RUNNER_TEMP": str(root),
                "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary),
            }

            subprocess.run(["bash", "-n"], input=script, text=True, check=True)
            subprocess.run(
                ["bash"],
                input=script,
                text=True,
                check=True,
                env=environment,
            )
            immutable_image = f"private.azurecr.io/mlops/online-runtime@{digest}"
            self.assertEqual(
                f"immutable_image={immutable_image}\n",
                output.read_text(),
            )
            self.assertIn(immutable_image, summary.read_text())
            self.assertFalse(Path(auth_path_log.read_text()).exists())

            environment["FAKE_DIGEST"] = "sha256:not-a-valid-digest"
            output.unlink()
            result = subprocess.run(
                ["bash"],
                input=script,
                text=True,
                env=environment,
                capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertIn(
                "Kaniko did not report a SHA-256 manifest digest",
                result.stderr,
            )

    def test_runner_update_and_bootstrap_assert_remote_exit_code(self):
        workflow_root = PATTERN_ROOT / "mlops" / "github-actions"
        update = (workflow_root / "update-runner-image.yml").read_text()
        bootstrap = PATTERN_ROOT / "runner-bootstrap"
        helper = (bootstrap / "scripts" / "invoke_aks_command.py").read_text()
        scripts = {
            name: (bootstrap / "scripts" / name).read_text()
            for name in ("install_arc.sh", "verify.sh", "uninstall.sh")
        }

        self.assertIn("runner_image:", update)
        self.assertEqual(2, update.count("runs-on: ubuntu-24.04"))
        self.assertNotIn("runs-on: mlops-private", update)
        self.assertIn(
            "AKS_CLUSTER_RESOURCE_ID: ${{ vars.ARC_AKS_CLUSTER_RESOURCE_ID }}",
            update,
        )
        self.assertIn(
            'aks_cluster_resource_id_lower="${AKS_CLUSTER_RESOURCE_ID,,}"', update
        )
        self.assertIn("/resourcegroups/", update)
        self.assertIn("ghcr.io/${GITHUB_REPOSITORY,,}-arc-runner@sha256:", update)
        self.assertEqual(2, update.count("invoke_aks_command.py"))
        self.assertIn('command="set -eu;', update)
        self.assertNotIn('command="set -euo pipefail;', update)
        self.assertNotIn("--output none", update)
        self.assertNotIn("az aks command invoke", update)
        self.assertIn("trap 'rm -f", update)
        self.assertIn("helm get values", update)
        self.assertIn(
            ".template.spec.containers |= map("
            'if .name == \\"runner\\" then .image = \\$image else . end)',
            update,
        )
        self.assertIn('"provisioningState"', helper)
        self.assertIn('"exitCode"', helper)
        self.assertIn("capture_output=True", helper)
        self.assertIn("SENSITIVE_VALUE", helper)
        for content in scripts.values():
            self.assertIn("invoke_aks_command.py", content)
            self.assertNotIn("az aks command invoke", content)

    def test_runner_build_requires_anonymous_public_package(self):
        build = (
            PATTERN_ROOT / "mlops" / "github-actions" / "build-runner-image.yml"
        ).read_text()
        anonymous_step = build.split(
            "      - name: Verify anonymous runner image pull",
            1,
        )[1].split("      - name: Report immutable image", 1)[0]

        self.assertIn("printf '{\"auths\":{}}\\n'", anonymous_step)
        self.assertIn('DOCKER_CONFIG="$anonymous_config"', anonymous_step)
        self.assertIn(
            'docker buildx imagetools inspect "$IMAGE_NAME@$DIGEST"',
            anonymous_step,
        )
        self.assertIn("trap cleanup EXIT", anonymous_step)
        self.assertIn('rm -f "$anonymous_config/config.json"', anonymous_step)
        self.assertIn("Set the GHCR package visibility to Public", anonymous_step)
        self.assertIn(
            "Do not add an imagePullSecret, PAT, or expiring token", anonymous_step
        )
        for prohibited in (
            "--method PATCH",
            "GITHUB_TOKEN",
            "password:",
            "username:",
            "docker login",
        ):
            self.assertNotIn(prohibited, anonymous_step)


if __name__ == "__main__":
    unittest.main()
