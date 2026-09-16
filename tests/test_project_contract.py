import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = ROOT / "classical" / "python-sdk-v2"
SCRIPT_ROOT = PATTERN_ROOT / "mlops" / "scripts"
TEMPLATE_REPOSITORY = "pgabriel-01/mlops-templates"
TEMPLATE_REF = "a8e5fcb5240e20e912cb1760adddec7efde57006"
BATCH_ENVIRONMENT = (
    "azureml://registries/azureml/environments/sklearn-1.5/versions/53"
)
TEMPLATE_BLOBS = {
    "src/python-sdk-v2/aml_client.py": ("d65c7d1fbf7287a9b1ab64a7025eb320dfac3a68"),
    ".github/workflows/python-sdk-v2-train-register.yml": (
        "16504df1fca114dcb8f5105f51baa115b2814527"
    ),
    ".github/workflows/python-sdk-v2-batch.yml": (
        "4a9532ed02a6c3ff6eedb66617a4f7c5b67adbd7"
    ),
    ".github/workflows/python-sdk-v2-online.yml": (
        "aa82d72db8fcb5c0fd60303d40efb7a38c55a623"
    ),
    "src/python-sdk-v2/create_batch_endpoint.py": (
        "c8be7b6e9f15c4f80a0980156eeaba45319459bc"
    ),
    "src/python-sdk-v2/create_batch_deployment.py": (
        "2d293cf2af536aa272369fa9736bb1f7bc172b86"
    ),
    "src/python-sdk-v2/test_batch_endpoint.py": (
        "de162e28504f710fe02b8380fadf631ce3456269"
    ),
    "src/python-sdk-v2/create_online_endpoint.py": (
        "388c0bef31c2ee2647dddca2fe91f5335c28284d"
    ),
    "src/python-sdk-v2/create_online_deployment.py": (
        "2d635b99fe710e458a466154eceba852c4670e96"
    ),
    "tests/test_python_sdk_v2.py": "f1fad04c0d3b93b113624474a98db2ad9374e264",
}
sys.path.insert(0, str(SCRIPT_ROOT))

from project_config import load_config
from validate_project import validate_config_values


def load_pinned_template(path: str) -> str:
    url = (
        f"https://raw.githubusercontent.com/{TEMPLATE_REPOSITORY}/"
        f"{TEMPLATE_REF}/{path}"
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        content = response.read()
    git_blob = hashlib.sha1(
        f"blob {len(content)}\0".encode() + content,
        usedforsecurity=False,
    ).hexdigest()
    if git_blob != TEMPLATE_BLOBS[path]:
        raise AssertionError(f"{path} at {TEMPLATE_REF} has unexpected blob {git_blob}")
    return content.decode()


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
                )
                .replace(
                    "manage_runner_hub_to_workload_peering: false",
                    "manage_runner_hub_to_workload_peering: true",
                )
                .replace(
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
        missing_hub_for_dns["shared_private_dns_zone_resource_ids"] = json.dumps(
            {"privatelink.blob.core.windows.net": shared_zone_id}
        )
        self.assertTrue(validate_config_values(path, missing_hub_for_dns))

        invalid_zone_mapping = dict(config)
        invalid_zone_mapping["runner_hub_vnet_resource_id"] = runner_hub_id
        invalid_zone_mapping["shared_private_dns_zone_resource_ids"] = json.dumps(
            {"privatelink.blob.core.windows.net": shared_zone_id + "-wrong"}
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
            self.assertIn("sdk_repository: __MLOPS_TEMPLATES_REPOSITORY__", content)
            self.assertIn("sdk_ref: __MLOPS_TEMPLATES_REF__", content)

    def test_batch_caller_exposes_immutable_environment(self):
        content = (
            PATTERN_ROOT
            / "mlops"
            / "github-actions"
            / "deploy-batch-endpoint.yml"
        ).read_text()

        self.assertIn(f"default: {BATCH_ENVIRONMENT}", content)
        self.assertIn(
            "deployment_environment: ${{ inputs.deployment_environment }}",
            content,
        )
        self.assertNotIn("conda_file:", content)
        self.assertNotIn("image:", content)
        self.assertNotIn(":latest", content)

    def test_workflows_use_generated_project_paths(self):
        workflow_root = PATTERN_ROOT / "mlops" / "github-actions"
        infrastructure = (workflow_root / "deploy-infrastructure.yml").read_text()
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
        self.assertIn(
            f"deployment_environment: {CURATED_BATCH_ENVIRONMENT}",
            batch,
        )
        self.assertNotIn("conda_file:", batch)

        for content in (training, online, batch):
            self.assertIn("mlops/scripts/export_config.py", content)
            self.assertNotIn("classical/python-sdk-v2/", content)

    def test_training_job_uses_immutable_curated_environment(self):
        job = (PATTERN_ROOT / "mlops" / "azureml" / "train" / "job.yml").read_text()

        environment_lines = [
            line.strip()
            for line in job.splitlines()
            if line.strip().startswith("environment:")
        ]
        self.assertEqual(
            [f"environment: {BATCH_ENVIRONMENT}"] * 3,
            environment_lines,
        )
        self.assertNotIn("conda_file:", job)
        self.assertNotIn(":latest", job)

    def test_documented_sparse_checkout_produces_runnable_tree(self):
        template_repository = TEMPLATE_REPOSITORY
        template_ref = TEMPLATE_REF

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
                project / ".github" / "workflows" / "deploy-infrastructure.yml"
            ).read_text()
            training_workflow = (
                project / ".github" / "workflows" / "train-register-model.yml"
            ).read_text()
            online_workflow = (
                project / ".github" / "workflows" / "deploy-online-endpoint.yml"
            ).read_text()
            batch_workflow = (
                project / ".github" / "workflows" / "deploy-batch-endpoint.yml"
            ).read_text()
            training_job = (
                project / "mlops" / "azureml" / "train" / "job.yml"
            ).read_text()
            self.assertIn("infrastructure/main.bicep", infrastructure_workflow)
            self.assertIn(
                "mlops/scripts/render_bicep_parameters.py",
                infrastructure_workflow,
            )
            self.assertIn(
                f"{template_repository}/.github/workflows/"
                f"python-sdk-v2-train-register.yml@{template_ref}",
                training_workflow,
            )
            self.assertIn(
                f"sdk_repository: {template_repository}",
                training_workflow,
            )
            self.assertIn(f"sdk_ref: {template_ref}", training_workflow)
            for workflow, reusable_name in (
                (training_workflow, "python-sdk-v2-train-register.yml"),
                (online_workflow, "python-sdk-v2-online.yml"),
                (batch_workflow, "python-sdk-v2-batch.yml"),
            ):
                self.assertIn(
                    f"{template_repository}/.github/workflows/"
                    f"{reusable_name}@{template_ref}",
                    workflow,
                )
                self.assertIn(
                    f"sdk_repository: {template_repository}",
                    workflow,
                )
                self.assertIn(f"sdk_ref: {template_ref}", workflow)
                self.assertNotIn("__MLOPS_TEMPLATES_", workflow)
            self.assertIn(
                f"default: {BATCH_ENVIRONMENT}",
                batch_workflow,
            )
            self.assertIn(
                "deployment_environment: "
                "${{ inputs.deployment_environment }}",
                batch_workflow,
            )
            self.assertNotIn("conda_file:", batch_workflow)
            self.assertNotIn("image:", batch_workflow)
            self.assertNotIn(":latest", batch_workflow)
            generated_environment_lines = [
                line.strip()
                for line in training_job.splitlines()
                if line.strip().startswith("environment:")
            ]
            self.assertEqual(
                [f"environment: {BATCH_ENVIRONMENT}"] * 3,
                generated_environment_lines,
            )
            self.assertNotIn("conda_file:", training_job)
            self.assertNotIn(":latest", training_job)
            self.assertTrue(
                project.joinpath("mlops", "azureml", "train", "job.yml").is_file()
            )
            self.assertTrue(
                project.joinpath("mlops", "scripts", "export_config.py").is_file()
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
        repository = TEMPLATE_REPOSITORY
        commit = TEMPLATE_REF
        for path in (PATTERN_ROOT / "mlops" / "github-actions").glob("*.yml"):
            rendered = (
                path.read_text()
                .replace("__MLOPS_TEMPLATES_REPOSITORY__", repository)
                .replace("__MLOPS_TEMPLATES_REF__", commit)
            )
            self.assertNotIn("__MLOPS_TEMPLATES_", rendered)
        self.assertEqual(40, len(commit))

    def test_no_stale_python_sdk_v2_template_pin(self):
        stale_prefixes = ("40e6" + "c55e", "d85f" + "2875")
        paths = [
            PATTERN_ROOT / "README.md",
            *PATTERN_ROOT.joinpath("mlops", "github-actions").glob("*.yml"),
        ]
        for path in paths:
            content = path.read_text()
            for stale_prefix in stale_prefixes:
                self.assertNotIn(stale_prefix, content)

    @unittest.skipUnless(
        os.environ.get("VERIFY_REMOTE_TEMPLATES") == "1",
        "set VERIFY_REMOTE_TEMPLATES=1 to verify immutable shared assets",
    )
    def test_pinned_templates_preserve_deployment_contracts_and_diagnostics(self):
        aml_client = load_pinned_template("src/python-sdk-v2/aml_client.py")
        training_workflow = load_pinned_template(
            ".github/workflows/python-sdk-v2-train-register.yml"
        )
        batch_workflow = load_pinned_template(
            ".github/workflows/python-sdk-v2-batch.yml"
        )
        online_workflow = load_pinned_template(
            ".github/workflows/python-sdk-v2-online.yml"
        )
        batch_endpoint = load_pinned_template(
            "src/python-sdk-v2/create_batch_endpoint.py"
        )
        batch_deployment = load_pinned_template(
            "src/python-sdk-v2/create_batch_deployment.py"
        )
        batch_invocation = load_pinned_template(
            "src/python-sdk-v2/test_batch_endpoint.py"
        )
        online_endpoint = load_pinned_template(
            "src/python-sdk-v2/create_online_endpoint.py"
        )
        online_deployment = load_pinned_template(
            "src/python-sdk-v2/create_online_deployment.py"
        )
        template_tests = load_pinned_template("tests/test_python_sdk_v2.py")

        self.assertIn("wait_for_poller(begin_create_or_update())", aml_client)
        self.assertIn("except ResourceExistsError as exc:", aml_client)
        self.assertIn("for attempt in range(1, max_update_attempts + 1):", aml_client)
        self.assertIn("return wait_for_resource_terminal_state(", aml_client)
        self.assertIn("if state in SUCCESS_PROVISIONING_STATES:", aml_client)
        self.assertIn("if state in FAILED_PROVISIONING_STATES:", aml_client)
        self.assertIn("raise TimeoutError(", aml_client)

        workflow_steps = (
            "Create or update endpoint",
            "Create or update default deployment",
            "Invoke endpoint and require successful completion",
        )
        self.assertEqual(
            sorted(batch_workflow.index(step) for step in workflow_steps),
            [batch_workflow.index(step) for step in workflow_steps],
        )
        self.assertIn(
            ".mlops-python-sdk/src/python-sdk-v2/create_batch_endpoint.py",
            batch_workflow,
        )
        self.assertIn(
            ".mlops-python-sdk/src/python-sdk-v2/create_batch_deployment.py",
            batch_workflow,
        )
        self.assertIn(
            ".mlops-python-sdk/src/python-sdk-v2/test_batch_endpoint.py",
            batch_workflow,
        )
        self.assertIn(
            "ref: ${{ inputs.sdk_ref }}",
            batch_workflow,
        )
        self.assertIn(
            f"default: {BATCH_ENVIRONMENT}",
            batch_workflow,
        )
        self.assertIn(
            "DEPLOYMENT_ENVIRONMENT: ${{ inputs.deployment_environment }}",
            batch_workflow,
        )
        self.assertIn('--environment "$DEPLOYMENT_ENVIRONMENT"', batch_workflow)
        self.assertIn("wait_for_resource_create_or_update(", batch_endpoint)
        self.assertIn("wait_for_resource_create_or_update(", batch_deployment)
        self.assertIn("DEFAULT_BATCH_ENVIRONMENT", batch_deployment)
        self.assertIn("type=validate_immutable_environment_reference", batch_deployment)
        self.assertIn("default=DEFAULT_BATCH_ENVIRONMENT", batch_deployment)
        self.assertIn("environment=environment", batch_deployment)
        self.assertIn("IMMUTABLE_ENVIRONMENT_PATTERNS", batch_deployment)
        self.assertNotIn("conda_file", batch_deployment)
        self.assertNotIn("Environment(", batch_deployment)
        self.assertIn(
            "DEPLOYMENT_ENVIRONMENT: ${{ inputs.deployment_environment }}",
            batch_workflow,
        )
        self.assertIn(
            f"default: {BATCH_ENVIRONMENT}",
            batch_workflow,
        )
        self.assertIn(
            '--environment "$DEPLOYMENT_ENVIRONMENT"',
            batch_workflow,
        )
        self.assertIn(
            "type=validate_immutable_environment_reference",
            batch_deployment,
        )
        self.assertIn("environment=environment", batch_deployment)
        self.assertLess(
            batch_deployment.index(
                "environment = validate_immutable_environment_reference("
                "args.environment)"
            ),
            batch_deployment.index("ml_client = create_ml_client(args)"),
        )
        self.assertNotIn("CondaConfiguration", batch_deployment)
        self.assertNotIn("code_configuration=", batch_deployment)
        self.assertNotIn("image=", batch_deployment)
        self.assertIn(
            "return wait_for_job(ml_client, invocation.name)", batch_invocation
        )
        for test_name in (
            "test_batch_endpoint_poller_completes_before_deployment_begin",
            "test_batch_deployment_poller_completes_before_invocation",
            "test_batch_endpoint_repeat_update_waits_then_retries",
            "test_batch_endpoint_terminal_operation_failure_propagates",
            "test_batch_deployment_uses_explicit_immutable_environment",
            "test_batch_deployment_rejects_mutable_environment_reference",
            "test_batch_workflow_uses_pinned_curated_environment",
            "test_batch_cli_defaults_to_immutable_prebuilt_environment",
        ):
            self.assertIn(test_name, template_tests)
        self.assertIn(
            '"image" not in batch_deployment_type.call_args.kwargs', template_tests
        )
        self.assertIn(
            '"code_configuration" not in batch_deployment_type.call_args.kwargs',
            template_tests,
        )
        self.assertIn("/versions/latest", template_tests)
        self.assertIn('"conda.yml"', template_tests)
        self.assertIn("create_client.assert_not_called()", template_tests)

        for required_input in (
            "compute:",
            "environment_name:",
            "environment_version:",
            "instance_type:",
        ):
            self.assertIn(required_input, online_workflow)
        self.assertNotIn("Standard_DS2_v2", online_workflow)
        self.assertNotIn("ubuntu-24.04", online_workflow)
        self.assertIn('--compute "$COMPUTE"', online_workflow)
        self.assertIn('--environment_name "$ENVIRONMENT_NAME"', online_workflow)
        self.assertIn('--environment_version "$ENVIRONMENT_VERSION"', online_workflow)
        self.assertIn("KubernetesOnlineEndpoint", online_endpoint)
        self.assertIn("get_kubernetes_online_compute", online_endpoint)
        self.assertIn("KubernetesOnlineDeployment", online_deployment)
        self.assertIn("get_prebuilt_environment", online_deployment)
        self.assertNotIn("ManagedOnlineEndpoint", online_endpoint)
        self.assertNotIn("ManagedOnlineDeployment", online_deployment)
        for test_name in (
            "test_online_workflow_requires_private_kubernetes_contract",
            "test_online_endpoint_uses_attached_arc_kubernetes_compute",
            "test_online_compute_requires_dedicated_namespace_and_uami",
            "test_prebuilt_environment_contract_requires_digest_and_no_build",
            "test_online_deployment_uses_kubernetes_and_exact_environment",
            "test_online_endpoint_completes_before_deployment_begins",
        ):
            self.assertIn(test_name, template_tests)
        self.assertIn(
            'batch_deployment_type.call_args.kwargs["environment"]',
            template_tests,
        )
        for mutable_reference in (
            "labels/latest",
            "versions/latest",
            "azureml:sklearn-1.5@latest",
            "mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest",
            "conda.yml",
        ):
            self.assertIn(mutable_reference, template_tests)

        self.assertIn("diagnostic_jobs = failed_children or [job]", aml_client)
        self.assertRegex(
            aml_client,
            r"(?s)ml_client\.jobs\.download\(\s*" r"name=job_name,.*?all=False,\s*\)",
        )
        self.assertIn("No log files found in standard diagnostics", aml_client)
        self.assertRegex(
            aml_client,
            r"(?s)No log files found.*?"
            r"ml_client\.jobs\.download\(\s*"
            r"name=job_name,.*?all=True,\s*\)",
        )
        self.assertIn("Unable to download diagnostics for job", aml_client)
        self.assertIn("[REDACTED]", aml_client)
        self.assertIn("diagnostic output truncated", aml_client)

        self.assertIn(
            "test_failed_job_downloads_child_logs_and_surfaces_root_cause",
            template_tests,
        )
        self.assertIn(
            "test_failed_job_reports_download_failure_and_falls_back_to_parent",
            template_tests,
        )
        self.assertIn(
            "test_failed_leaf_retries_full_download_when_standard_download_is_pointer",
            template_tests,
        )
        self.assertIn("Traceback (most recent call last)", template_tests)
        self.assertIn("error=None", template_tests)

        self.assertIn("if: ${{ failure() }}", training_workflow)
        self.assertIn(
            "actions/upload-artifact@" "ea165f8d65b6e75b540449e92b4886f43607fa02",
            training_workflow,
        )
        self.assertIn("path: aml-diagnostics", training_workflow)
        self.assertIn(
            "name: aml-diagnostics-${{ "
            "steps.train.outputs.training_job_name || github.run_id }}",
            training_workflow,
        )
        self.assertIn("if-no-files-found: warn", training_workflow)

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
        self.assertNotIn("managedNetwork:", workspace)
        self.assertNotIn("isolationMode:", workspace)
        self.assertNotIn("serverlessComputeSettings:", workspace)
        self.assertNotIn("serverlessComputeCustomSubnet", workspace)
        self.assertIn(
            "publicNetworkAccess: enableNetworkIsolation ? 'Disabled' : 'Enabled'",
            workspace,
        )
        self.assertIn(
            "enableNodePublicIp: empty(subnetId)",
            (
                ROOT / "infrastructure/bicep/modules/aml_computecluster.bicep"
            ).read_text(),
        )
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
        self.assertIn(
            "registrationEnabled: false",
            (
                ROOT / "infrastructure/bicep/modules/private_dns_zone_vnet_link.bicep"
            ).read_text(),
        )

    def test_workspace_and_compute_use_custom_vnet_only(self):
        workspace = (
            ROOT / "infrastructure/bicep/modules/aml_workspace.bicep"
        ).read_text()
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()

        forbidden_workspace_network_properties = (
            "managedNetwork:",
            "isolationMode:",
            "serverlessComputeSettings:",
            "serverlessComputeCustomSubnet",
        )

        self.assertFalse(
            any(
                property_name in workspace
                for property_name in forbidden_workspace_network_properties
            )
        )
        self.assertNotIn("param computeSubnetId", workspace)
        self.assertNotIn("computeSubnetId:", main)
        self.assertIn(
            "publicNetworkAccess: enableNetworkIsolation ? 'Disabled' : 'Enabled'",
            workspace,
        )
        self.assertIn(
            "subnetId: enableVNet ? vnet!.outputs.computeSubnetId : ''",
            main,
        )
        self.assertIn(
            "enableNodePublicIp: empty(subnetId)",
            (
                ROOT / "infrastructure/bicep/modules/aml_computecluster.bicep"
            ).read_text(),
        )
        self.assertIn("module peMlw './modules/private_endpoint.bicep'", main)

    def test_private_compute_compiles_with_workspace_endpoint_dependency(self):
        main_path = ROOT / "infrastructure/bicep/main.bicep"
        main = main_path.read_text()

        self.assertRegex(
            main,
            r"(?s)module mlwcc .*?dependsOn:\s*\[\s*peMlw\s*\]",
        )

        completed = subprocess.run(
            [
                "az",
                "bicep",
                "build",
                "--stdout",
                "--file",
                str(main_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        template = json.loads(completed.stdout)
        compute_deployment = next(
            resource
            for resource in template["resources"]
            if resource.get("name") == "mlwcc"
        )
        endpoint_deployment = next(
            resource
            for resource in template["resources"]
            if resource.get("name") == "pe-mlw"
        )

        self.assertTrue(
            any(
                "'Microsoft.Resources/deployments', 'pe-mlw'" in dependency
                for dependency in compute_deployment["dependsOn"]
            )
        )
        self.assertEqual(
            compute_deployment["condition"],
            "[parameters('enableComputeCluster')]",
        )
        self.assertEqual(
            endpoint_deployment["condition"],
            "[parameters('enableVNet')]",
        )

    def test_key_vault_name_stays_within_exact_azure_boundary(self):
        main = (ROOT / "infrastructure/bicep/main.bicep").read_text()
        key_vault = (ROOT / "infrastructure/bicep/modules/key_vault.bicep").read_text()

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
            ROOT / "infrastructure/bicep/modules/private_dns_zone_vnet_link.bicep"
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
