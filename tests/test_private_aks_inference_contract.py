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
    def _runner_update_script():
        update = (
            PATTERN_ROOT / "mlops" / "github-actions" / "update-runner-image.yml"
        ).read_text()
        update_step = update.split(
            "      - name: Update immutable ARC runner image",
            1,
        )[1].split("\n\n  reconcile:", 1)[0]
        return textwrap.dedent(update_step.split("        run: |\n", 1)[1])

    def test_disabled_defaults_are_safe_and_rendered(self):
        config_path = PATTERN_ROOT / "config-infra-dev.yml"
        config = load_config(config_path)
        self.assertFalse(config["enable_private_aks_inference"])
        self.assertEqual("", config["aks_cluster_resource_id"])
        self.assertEqual("", config["aks_node_subnet_resource_id"])
        self.assertEqual("aks-inference", config["online_compute"])
        self.assertTrue(config["online_mlflow_no_code"])
        self.assertEqual("", config["online_environment_name"])
        self.assertEqual("", config["online_environment_version"])
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
            self.assertTrue(parameters["onlineMlflowNoCode"]["value"])
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
            "online_mlflow_no_code": False,
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
            "online_environment_name": "taxi-inference",
            "online_environment_version": "1",
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
            "missing environment image": {"online_environment_image": ""},
            "missing environment name": {"online_environment_name": ""},
            "missing environment version": {"online_environment_version": ""},
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

        no_code = {
            **valid,
            "online_mlflow_no_code": True,
            "online_environment_name": "",
            "online_environment_version": "",
            "online_environment_image": "",
        }
        self.assertEqual([], validate_config_values(config_path, no_code))
        for field in (
            "online_environment_name",
            "online_environment_version",
            "online_environment_image",
        ):
            with self.subTest(no_code_conflict=field):
                self.assertTrue(
                    validate_config_values(
                        config_path,
                        {**no_code, field: valid[field]},
                    )
                )

        disabled_partial_image_only = {
            **base,
            "online_mlflow_no_code": False,
            "online_environment_name": "taxi-inference",
        }
        self.assertTrue(
            validate_config_values(config_path, disabled_partial_image_only)
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
        self.assertNotIn("Microsoft.Resources/deploymentScripts", main + cluster)
        self.assertNotIn("azCliVersion", main + cluster)
        self.assertNotIn("az aks command invoke", main + cluster)
        self.assertIn("namespaceBootstrapPrincipalId", cluster)
        self.assertIn("principalId: namespaceBootstrapPrincipalId", cluster)
        self.assertNotIn(
            "principalId: workspaceManagedIdentityPrincipalId\n"
            "    principalType: 'ServicePrincipal'\n"
            "    roleDefinitionId: namespaceBootstrapRoleId",
            cluster,
        )
        self.assertIn("if (deployExtension)", cluster)
        self.assertIn("completePrivateAksInferenceDeployment", main)
        self.assertIn(
            "if (enablePrivateAksInference && completePrivateAksInferenceDeployment)",
            main,
        )
        self.assertIn("releaseTrain: extensionReleaseTrain", cluster)
        self.assertIn("federatedIdentityCredentials@2024-11-30", identity)
        self.assertIn("storageBlobDataReaderRoleId", identity)
        self.assertIn("computeType: 'Kubernetes'", compute)
        self.assertIn("identityId", compute)
        self.assertIn("workspaces/environments/versions@2025-06-01", environment)
        self.assertIn("image: validatedImageUri", environment)
        self.assertIn("fail('The image-only online environment", environment)
        self.assertNotIn("build:", environment)
        self.assertNotIn("condaFile:", environment)
        self.assertIn("param onlineMlflowNoCode bool = true", main)
        self.assertIn(
            "if (enablePrivateAksInference && !onlineMlflowNoCode)",
            main,
        )
        compute_module = main.split(
            "module amlKubernetesCompute",
            1,
        )[1].split(
            "// AML Registry", 1
        )[0]
        self.assertNotIn("amlOnlineEnvironment", compute_module)
        self.assertIn("fail('MLflow no-code mode cannot define", main)
        self.assertIn("fail('Image-only mode requires", main)
        self.assertIn("output onlineConfigurationValidated bool", main)
        self.assertNotIn("listKeys(", main + cluster + identity + compute)
        self.assertNotIn("enableNodePublicIP: true", cluster)
        self.assertIn("clusterResourceId: aksClusterResourceId", main)

    def test_workflow_bootstraps_namespace_without_deployment_scripts(self):
        workflow = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-infrastructure.yml"
        ).read_text()

        self.assertIn("completePrivateAksInferenceDeployment=false", workflow)
        self.assertIn("legacyNamespaceBootstrapRoleAssignmentId", workflow)
        self.assertIn("az role assignment delete --ids", workflow)
        self.assertIn(
            "Legacy workspace identity namespace bootstrap role assignment still exists",
            workflow,
        )
        self.assertIn("invoke_aks_command.py", workflow)
        self.assertIn('--file "$namespace_manifest"', workflow)
        self.assertIn(
            '--command "kubectl apply -f $(basename "$namespace_manifest")"',
            workflow,
        )
        self.assertIn("for attempt in $(seq 1 12)", workflow)
        self.assertIn('if [[ "$bootstrap_succeeded" != "true" ]]', workflow)
        self.assertNotIn("az aks command invoke", workflow)
        bootstrap = workflow.split(
            "            bootstrap_outputs=",
            1,
        )[1].split(
            "          az deployment sub create",
            1,
        )[0]
        self.assertNotIn("|| true", bootstrap)

    def test_no_code_workflow_retires_runtime_builder(self):
        runtime_root = PATTERN_ROOT / "mlops" / "online-runtime"
        publish = (
            PATTERN_ROOT / "mlops" / "github-actions" / "publish-online-runtime.yml"
        )
        runner_dockerfile = (
            PATTERN_ROOT / "runner-bootstrap" / "image" / "Dockerfile"
        ).read_text()
        runner_smoke = (
            PATTERN_ROOT / "mlops" / "github-actions" / "runner-smoke-test.yml"
        ).read_text()
        deploy = (
            PATTERN_ROOT / "mlops" / "github-actions" / "deploy-infrastructure.yml"
        ).read_text()

        self.assertFalse(runtime_root.exists())
        self.assertFalse(publish.exists())
        self.assertNotIn("kaniko", runner_dockerfile.lower())
        self.assertIn("USER runner", runner_dockerfile)
        self.assertIn("test ! -S /var/run/docker.sock", runner_smoke)
        self.assertNotIn("kaniko", runner_smoke.lower())
        self.assertIn("runner_image:", runner_smoke)
        self.assertIn(
            "AKS_CLUSTER_RESOURCE_ID: ${{ vars.ARC_AKS_CLUSTER_RESOURCE_ID }}",
            runner_smoke,
        )
        self.assertIn("invoke_aks_command.py", runner_smoke)
        self.assertIn("--logs-output", runner_smoke)
        self.assertIn("trap 'rm -f", runner_smoke)
        self.assertIn('"$live_image" == "$EXPECTED_RUNNER_IMAGE"', runner_smoke)
        self.assertNotIn("az aks command invoke", runner_smoke)
        self.assertNotIn("--query logs", runner_smoke)
        self.assertNotIn("--output tsv", runner_smoke)
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
        pattern_documentation = (PATTERN_ROOT / "README.md").read_text()
        runner_documentation = (
            PATTERN_ROOT / "runner-bootstrap" / "README.md"
        ).read_text()
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
        for content in (documentation, pattern_documentation, runner_documentation):
            self.assertIn("MLflow no-code", content)
            self.assertIn("image-only", content)
        self.assertIn("chown /", documentation)
        self.assertNotIn("publish-online-runtime.yml", documentation)

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
        self.assertNotIn("helm get values", update)
        self.assertNotIn("helm upgrade", update)
        self.assertNotIn("kubectl get secret", update)
        self.assertNotIn("kubectl get secrets", update)
        self.assertNotIn("rolebinding", update.lower())
        self.assertNotIn("clusterrole", update.lower())
        self.assertIn(
            "AutoscalingRunnerSet must contain exactly one runner container",
            update,
        )
        self.assertIn(
            "runner_count=\\$(jq "
            "'[.spec.template.spec.containers | to_entries[] | "
            'select(.value.name == \\"runner\\")] | length\'',
            update,
        )
        self.assertIn(
            "runner_index=\\$(jq -r "
            "'.spec.template.spec.containers | to_entries[] | "
            'select(.value.name == \\"runner\\") | .key\'',
            update,
        )
        self.assertIn(
            "case \\\"\\$runner_index\\\" in ''|*[!0-9]*)",
            update,
        )
        self.assertIn(
            "jq -cn --arg image '$RUNNER_IMAGE' "
            '--argjson index \\"\\$runner_index\\"',
            update,
        )
        self.assertIn(
            '\\"op\\":\\"replace\\",\\"path\\":('
            '\\"/spec/template/spec/containers/\\" + '
            '(\\$index | tostring) + \\"/image\\"),'
            '\\"value\\":\\$image',
            update,
        )
        self.assertIn(
            "kubectl patch autoscalingrunnerset mlops-private "
            "--namespace arc-runners --type json --patch-file",
            update,
        )
        self.assertIn(
            "kubectl get autoscalingrunnerset mlops-private "
            "--namespace arc-runners --output json | jq -r "
            '--argjson index \\"\\$runner_index\\" '
            "'.spec.template.spec.containers[\\$index].image // empty'",
            update,
        )
        self.assertIn("test \\\"\\$actual\\\" = '$RUNNER_IMAGE'", update)
        self.assertIn('"provisioningState"', helper)
        self.assertIn('"exitCode"', helper)
        self.assertIn("capture_output=True", helper)
        self.assertIn("SENSITIVE_VALUE", helper)
        for content in scripts.values():
            self.assertIn("invoke_aks_command.py", content)
            self.assertNotIn("az aks command invoke", content)

    def test_runner_update_patches_only_unique_runner_image(self):
        script = self._runner_update_script()
        # The macOS system Bash predates the lowercase expansion used on Ubuntu.
        executable_script = script.replace(
            "${GITHUB_REPOSITORY,,}",
            "${GITHUB_REPOSITORY}",
        ).replace(
            "${AKS_CLUSTER_RESOURCE_ID,,}",
            "${AKS_CLUSTER_RESOURCE_ID}",
        )
        digest = "a" * 64
        immutable_image = (
            "ghcr.io/example/mlops-project-template-arc-runner@sha256:" + digest
        )
        base_resource = {
            "apiVersion": "actions.github.com/v1alpha1",
            "kind": "AutoscalingRunnerSet",
            "metadata": {"name": "mlops-private", "namespace": "arc-runners"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "sidecar",
                                "image": "example/sidecar@sha256:" + "b" * 64,
                            },
                            {
                                "name": "runner",
                                "image": "ghcr.io/example/old@sha256:" + "c" * 64,
                                "command": ["/home/runner/run.sh"],
                                "resources": {"requests": {"cpu": "500m"}},
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                },
                            },
                        ]
                    }
                }
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "resource.json"
            patch_log = root / "patch.json"
            state.write_text(json.dumps(base_resource))
            fake_python = root / "python3"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    command=
                    while [ "$#" -gt 0 ]; do
                      if [ "$1" = "--command" ]; then
                        command=$2
                        shift 2
                      else
                        shift
                      fi
                    done
                    test -n "$command"
                    /bin/sh -c "$command"
                    """
                )
            )
            fake_python.chmod(0o755)
            fake_kubectl = root / "kubectl"
            fake_kubectl.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    set -eu
                    operation=$1
                    shift
                    case "$operation" in
                      get)
                        cat "$FAKE_KUBECTL_STATE"
                        ;;
                      patch)
                        patch_file=
                        while [ "$#" -gt 0 ]; do
                          if [ "$1" = "--patch-file" ]; then
                            patch_file=$2
                            shift 2
                          else
                            shift
                          fi
                        done
                        test -n "$patch_file"
                        cp "$patch_file" "$FAKE_KUBECTL_PATCH_LOG"
                        index=$(jq -r '.[0].path | capture(
                          "^/spec/template/spec/containers/(?<index>[0-9]+)/image$"
                        ).index | tonumber' "$patch_file")
                        image=$(jq -r '.[0].value' "$patch_file")
                        updated=$(mktemp)
                        jq --argjson index "$index" --arg image "$image" \
                          '.spec.template.spec.containers[$index].image = $image' \
                          "$FAKE_KUBECTL_STATE" > "$updated"
                        mv "$updated" "$FAKE_KUBECTL_STATE"
                        ;;
                      *)
                        exit 2
                        ;;
                    esac
                    """
                )
            )
            fake_kubectl.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{root}:{os.environ['PATH']}",
                "AKS_CLUSTER_RESOURCE_ID": (
                    "/subscriptions/00000000-0000-0000-0000-000000000001/"
                    "resourcegroups/runner/providers/microsoft.containerservice/"
                    "managedclusters/private"
                ),
                "RUNNER_IMAGE": immutable_image,
                "GITHUB_REPOSITORY": "example/mlops-project-template",
                "FAKE_KUBECTL_STATE": str(state),
                "FAKE_KUBECTL_PATCH_LOG": str(patch_log),
            }

            subprocess.run(["bash", "-n"], input=script, text=True, check=True)
            subprocess.run(
                ["bash"],
                input=executable_script,
                text=True,
                check=True,
                cwd=PATTERN_ROOT,
                env=environment,
            )

            self.assertEqual(
                [
                    {
                        "op": "replace",
                        "path": "/spec/template/spec/containers/1/image",
                        "value": immutable_image,
                    }
                ],
                json.loads(patch_log.read_text()),
            )
            expected = json.loads(json.dumps(base_resource))
            expected["spec"]["template"]["spec"]["containers"][1][
                "image"
            ] = immutable_image
            self.assertEqual(expected, json.loads(state.read_text()))

            invalid_containers = (
                [base_resource["spec"]["template"]["spec"]["containers"][0]],
                [
                    base_resource["spec"]["template"]["spec"]["containers"][1],
                    {
                        "name": "runner",
                        "image": "ghcr.io/example/duplicate@sha256:" + "d" * 64,
                    },
                ],
            )
            for containers in invalid_containers:
                with self.subTest(runner_count=len(containers)):
                    resource = json.loads(json.dumps(base_resource))
                    resource["spec"]["template"]["spec"]["containers"] = containers
                    state.write_text(json.dumps(resource))
                    patch_log.unlink(missing_ok=True)
                    result = subprocess.run(
                        ["bash"],
                        input=executable_script,
                        text=True,
                        cwd=PATTERN_ROOT,
                        env=environment,
                        capture_output=True,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertFalse(patch_log.exists())
                    self.assertEqual(resource, json.loads(state.read_text()))

    def test_arc_operator_rbac_is_exact_and_installed_fail_closed(self):
        bootstrap = PATTERN_ROOT / "runner-bootstrap"
        install_path = bootstrap / "scripts" / "install_arc.sh"
        install = install_path.read_text()
        manifest = json.loads(
            (bootstrap / "manifests" / "arc-operator-rbac.json").read_text()
        )
        role, binding = manifest["items"]

        self.assertEqual("Role", role["kind"])
        self.assertEqual(
            {"name": "arc-image-update-operator", "namespace": "arc-runners"},
            role["metadata"],
        )
        self.assertEqual(
            [
                {
                    "apiGroups": ["actions.github.com"],
                    "resources": ["autoscalingrunnersets"],
                    "verbs": ["get", "patch"],
                },
                {
                    "apiGroups": ["actions.github.com"],
                    "resources": ["ephemeralrunnersets"],
                    "verbs": ["get", "list", "delete"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "delete"],
                },
            ],
            role["rules"],
        )
        allowed_resources = {
            resource for rule in role["rules"] for resource in rule["resources"]
        }
        allowed_verbs = {verb for rule in role["rules"] for verb in rule["verbs"]}
        self.assertTrue(
            {
                "secrets",
                "serviceaccounts",
                "pods/exec",
                "nodes",
                "roles",
                "rolebindings",
            }.isdisjoint(allowed_resources)
        )
        self.assertTrue(
            {"create", "update", "bind", "escalate", "impersonate"}.isdisjoint(
                allowed_verbs
            )
        )

        self.assertEqual("RoleBinding", binding["kind"])
        self.assertEqual(
            {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "arc-image-update-operator",
            },
            binding["roleRef"],
        )
        self.assertEqual(
            [
                {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "User",
                    "name": "__ARC_OPERATOR_PRINCIPAL_OBJECT_ID__",
                }
            ],
            binding["subjects"],
        )
        self.assertIn(
            "[[ ${ARC_OPERATOR_PRINCIPAL_OBJECT_ID:-} =~ " "^[0-9a-fA-F]{8}-",
            install,
        )
        self.assertIn(
            '--command "kubectl apply -f $(basename ' '"$RENDERED_OPERATOR_RBAC")"',
            install,
        )
        self.assertIn('--file "$RENDERED_OPERATOR_RBAC"', install)
        self.assertNotIn("Azure Kubernetes Service RBAC Writer", install)
        self.assertNotIn("Azure Kubernetes Service RBAC Admin", install)

        base_environment = {
            **os.environ,
            "ARC_RUNNER_IMAGE": (
                "ghcr.io/example/repository-arc-runner@sha256:" + "a" * 64
            ),
            "ARC_GITHUB_CONFIG_URL": "https://github.com/example/repository",
            "ARC_APP_METADATA": str(bootstrap / "missing-app.json"),
        }
        for principal in ("", "not-a-uuid"):
            with self.subTest(principal=principal):
                result = subprocess.run(
                    ["bash", install_path],
                    env={
                        **base_environment,
                        "ARC_OPERATOR_PRINCIPAL_OBJECT_ID": principal,
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "ARC_OPERATOR_PRINCIPAL_OBJECT_ID is required",
                    result.stderr,
                )

        result = subprocess.run(
            ["bash", install_path],
            env={
                **base_environment,
                "ARC_OPERATOR_PRINCIPAL_OBJECT_ID": (
                    "00000000-0000-4000-8000-000000000001"
                ),
            },
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Missing verified App metadata", result.stderr)
        self.assertNotIn("ARC_OPERATOR_PRINCIPAL_OBJECT_ID is required", result.stderr)

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
