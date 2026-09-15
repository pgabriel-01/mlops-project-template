from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

ENVIRONMENT_CONFIGS = {
    "dev": ROOT / "config-infra-dev.yml",
    "test": ROOT / "config-infra-test.yml",
    "prod": ROOT / "config-infra-prod.yml",
}

PIPELINES = [
    ROOT
    / "infrastructure/terraform/devops-pipelines/platform-ado-bootstrap.yml",
    ROOT / "infrastructure/terraform/devops-pipelines/tf-ado-deploy-infra.yml",
    ROOT
    / "classical/aml-cli-v2/mlops/devops-pipelines/deploy-model-training-pipeline.yml",
    ROOT
    / "classical/aml-cli-v2/mlops/devops-pipelines/deploy-online-endpoint-pipeline.yml",
    ROOT
    / "classical/aml-cli-v2/mlops/devops-pipelines/deploy-batch-endpoint-pipeline.yml",
]


class AzureDevOpsDeploymentWiringTests(unittest.TestCase):
    def test_environment_configs_use_variable_groups(self):
        for environment, path in ENVIRONMENT_CONFIGS.items():
            content = path.read_text()
            self.assertIn(f"- group: mlops-{environment}", content)
            self.assertIn(f"value: {environment}", content)
            self.assertIn(f"value: mlops-{environment}", content)
            self.assertNotIn("Azure-ARM-", content)

    def test_private_endpoint_posture_is_environment_specific(self):
        for environment in ("dev", "test", "prod"):
            self.assertIn(
                "value: true", ENVIRONMENT_CONFIGS[environment].read_text()
            )

    def test_pipelines_support_environment_pool_and_template_selection(self):
        for path in PIPELINES:
            content = path.read_text()
            self.assertIn("name: environment", content)
            self.assertIn("name: agentPoolName", content)
            self.assertIn("name: mlopsTemplatesRef", content)
            self.assertIn("default: refs/heads/main", content)
            self.assertIn("config-infra-dev.yml", content)
            self.assertIn("config-infra-test.yml", content)
            self.assertIn("config-infra-prod.yml", content)
            self.assertIn("ref: ${{ parameters.mlopsTemplatesRef }}", content)

            if path.name == "platform-ado-bootstrap.yml":
                self.assertIn("vmImage: $(ap_vm_image)", content)
                self.assertIn(
                    "templates/infra/platform-bootstrap.yml@mlops-templates",
                    content,
                )
            else:
                self.assertIn(
                    "value: ${{ coalesce(parameters.agentPoolName, "
                    "variables.managed_devops_pool_alias) }}",
                    content,
                )
                self.assertIn("name: $(selected_agent_pool)", content)
                self.assertNotIn(
                    "${{ elseif eq(variables.network_mode, 'private') }}",
                    content,
                )

    def test_factory_manifest_variables_are_available(self):
        common = (ROOT / "config-infra-common.yml").read_text()
        for variable in (
            "managed_devops_pool_name",
            "managed_devops_pool_alias",
            "managed_devops_pool_resource_group",
            "managed_devops_pool_location",
            "managed_devops_pool_vm_sku",
            "managed_devops_pool_subnet_address_prefix",
            "platform_vnet_name",
            "platform_vnet_address_prefix",
            "platform_private_endpoint_subnet_address_prefix",
        ):
            self.assertIn(variable, common)

        for environment, path in ENVIRONMENT_CONFIGS.items():
            content = path.read_text()
            expected_mode = "private"
            self.assertIn(f"value: {expected_mode}", content)
            self.assertIn("platform_service_connection_name", content)
            self.assertIn("workload_service_connection_name", content)

    def test_platform_bootstrap_matches_reusable_contract(self):
        content = PIPELINES[0].read_text()
        required_parameters = (
            "environment: ${{ parameters.environment }}",
            "devAzureServiceConnection",
            "testAzureServiceConnection",
            "prodAzureServiceConnection",
            "devCicdPrincipalObjectId",
            "testCicdPrincipalObjectId",
            "prodCicdPrincipalObjectId",
            "devOpsInfrastructurePrincipalObjectId",
            "resourceGroup",
            "virtualNetworkName",
            "stateStorageAccountName",
            "managedDevOpsPoolName",
            "managedDevOpsPoolAlias",
            "devCenterProjectResourceId",
        )
        for parameter in required_parameters:
            self.assertIn(parameter, content)

        for obsolete_parameter in (
            "azureServiceConnection:",
            "cicdPrincipalObjectId:",
            "managedDevOpsPoolResourceGroup:",
            "backendResourceGroup:",
        ):
            self.assertNotIn(obsolete_parameter, content)

    def test_private_workload_network_is_reachable_from_platform_pool(self):
        terraform = (ROOT / "infrastructure/terraform/aml_deploy.tf").read_text()
        for resource in (
            'azurerm_virtual_network_peering" "platform_to_workload',
            'azurerm_virtual_network_peering" "workload_to_platform',
            'azurerm_private_dns_zone_virtual_network_link" "workload_aml_zones_to_platform',
            'azurerm_private_dns_zone_virtual_network_link" "workload_service_zones_to_platform',
            'azurerm_private_dns_zone_virtual_network_link" "workload_blob_to_platform',
        ):
            self.assertIn(resource, terraform)

        self.assertIn('name                      = "peer-agents-to-workload"', terraform)
        self.assertIn('name                      = "peer-workload-to-agents"', terraform)
        self.assertIn(
            'name                  = "link-agents-${replace(each.value, ".", "_")}"',
            terraform,
        )
        self.assertEqual(terraform.count("import {\n"), 3)
        self.assertIn("var.import_existing_platform_connectivity", terraform)

        vnet_module = (
            ROOT / "infrastructure/terraform/modules/vnet/main.tf"
        ).read_text()
        self.assertNotIn("external_blob_private_dns_zone_id", vnet_module)

        variables = (ROOT / "infrastructure/terraform/variables.tf").read_text()
        self.assertIn('variable "platform_resource_group_name"', variables)
        self.assertIn('variable "platform_virtual_network_name"', variables)
        self.assertIn(
            'variable "import_existing_platform_connectivity"',
            variables,
        )

        pipeline = PIPELINES[1].read_text()
        self.assertIn(
            "platformResourceGroupName: $(managed_devops_pool_resource_group)",
            pipeline,
        )
        self.assertIn(
            "platformVirtualNetworkName: $(platform_vnet_name)",
            pipeline,
        )
        self.assertIn(
            "importExistingPlatformConnectivity: "
            "${{ parameters.importExistingPlatformConnectivity }}",
            pipeline,
        )
        self.assertIn("apply: ${{ parameters.applyTerraform }}", pipeline)

    def test_documentation_names_immutable_template_dependency(self):
        documentation = (ROOT / "docs/azure-devops-deployment.md").read_text()
        self.assertIn(
            "80a74134d9c6f6ebf0e1545e906685770d316b2a",
            documentation,
        )

    def test_monitoring_uses_supported_sku_after_key_vault_rbac(self):
        data_explorer = (
            ROOT / "infrastructure/terraform/modules/data-explorer/main.tf"
        ).read_text()
        self.assertIn('name     = "Standard_E2ads_v5"', data_explorer)
        self.assertNotIn("Standard_D11_v2", data_explorer)

        key_vault = (
            ROOT / "infrastructure/terraform/modules/key-vault/main.tf"
        ).read_text()
        self.assertIn('resource "time_sleep" "wait_for_rbac_propagation"', key_vault)
        self.assertIn('create_duration = "120s"', key_vault)

        terraform = (ROOT / "infrastructure/terraform/aml_deploy.tf").read_text()
        self.assertIn("depends_on = [\n    module.key_vault\n  ]", terraform)

    def test_workspace_system_datastores_use_identity_authentication(self):
        root = (ROOT / "infrastructure/terraform/main.tf").read_text()
        self.assertIn('source  = "Azure/azapi"', root)

        workspace = (
            ROOT / "infrastructure/terraform/modules/aml-workspace/main.tf"
        ).read_text()
        self.assertIn(
            'resource "azapi_update_resource" "identity_based_system_datastores"',
            workspace,
        )
        self.assertIn(
            'type        = "Microsoft.MachineLearningServices/workspaces@2025-06-01"',
            workspace,
        )
        self.assertIn('systemDatastoresAuthMode = "identity"', workspace)
        self.assertIn(
            "azapi_update_resource.identity_based_system_datastores",
            workspace,
        )

    def test_private_storage_supports_parallel_run_queue_and_table_services(self):
        root = (ROOT / "infrastructure/terraform/aml_deploy.tf").read_text()
        storage = (
            ROOT / "infrastructure/terraform/modules/storage-account/main.tf"
        ).read_text()
        storage_variables = (
            ROOT / "infrastructure/terraform/modules/storage-account/variables.tf"
        ).read_text()
        vnet = (ROOT / "infrastructure/terraform/modules/vnet/main.tf").read_text()
        vnet_outputs = (
            ROOT / "infrastructure/terraform/modules/vnet/outputs.tf"
        ).read_text()
        workspace = (
            ROOT / "infrastructure/terraform/modules/aml-workspace/main.tf"
        ).read_text()

        for service in ("queue", "table"):
            self.assertIn(
                f"private_dns_zone_{service}_id",
                root,
            )
            self.assertIn(
                f'variable "private_dns_zone_{service}_id"',
                storage_variables,
            )
            self.assertIn(
                f'resource "azurerm_private_endpoint" "st_{service}_pe"',
                storage,
            )
            self.assertIn(f'subresource_names              = ["{service}"]', storage)
            self.assertIn(
                f'name                = "privatelink.{service}.core.windows.net"',
                vnet,
            )
            self.assertIn(
                f"{service}         = azurerm_private_dns_zone.{service}.id",
                vnet_outputs,
            )
            self.assertIn(
                f"{service}         = azurerm_private_dns_zone.{service}.name",
                vnet_outputs,
            )
            self.assertIn(
                f'subresourceTarget = "{service}"',
                workspace,
            )

        for identity in ("mlw_uai", "mlw_system"):
            for service, role in (
                ("queue", "Storage Queue Data Contributor"),
                ("table", "Storage Table Data Contributor"),
            ):
                assignment = (
                    f'resource "azurerm_role_assignment" '
                    f'"{identity}_storage_{service}_data_contributor"'
                )
                self.assertIn(assignment, workspace)
                self.assertIn(f'role_definition_name = "{role}"', workspace)
                self.assertIn(
                    f"azurerm_role_assignment."
                    f"{identity}_storage_{service}_data_contributor",
                    workspace,
                )

    def test_private_workspace_uses_managed_network_without_public_compute_ips(self):
        root = (ROOT / "infrastructure/terraform/aml_deploy.tf").read_text()
        self.assertNotIn("training_subnet_id                =", root)
        self.assertNotIn("rg_id    = module.resource_group.id", root)

        variables = (
            ROOT / "infrastructure/terraform/modules/aml-workspace/variables.tf"
        ).read_text()
        self.assertNotIn('variable "training_subnet_id"', variables)
        self.assertNotIn('variable "rg_id"', variables)

        workspace = (
            ROOT / "infrastructure/terraform/modules/aml-workspace/main.tf"
        ).read_text()
        self.assertNotIn('dynamic "managed_network"', workspace)
        self.assertNotIn("provision_on_creation_enabled", workspace)
        self.assertIn("managedNetwork = {", workspace)
        self.assertIn('isolationMode = "AllowInternetOutbound"', workspace)
        self.assertIn("var.enable_private_endpoints ? {", workspace)
        self.assertIn(
            'resource "azapi_resource_action" "provision_managed_network" {\n'
            "  count = var.enable_private_endpoints ? 1 : 0",
            workspace,
        )
        self.assertIn(
            'type        = "Microsoft.MachineLearningServices/workspaces@2025-06-01"',
            workspace,
        )
        self.assertIn('action      = "provisionManagedNetwork"', workspace)
        self.assertIn('method      = "POST"', workspace)
        self.assertIn(
            "body = {\n    includeSpark = false\n  }",
            workspace,
        )
        self.assertEqual(
            workspace.count(
                'role_definition_name = "Azure AI Enterprise Network Connection Approver"'
            ),
            6,
        )
        for identity in ("mlw_uai", "mlw_system"):
            for target in ("storage", "keyvault", "acr"):
                self.assertIn(
                    f'resource "azurerm_role_assignment" "{identity}_{target}_network_connection_approver" {{\n'
                    "  count                = var.enable_private_endpoints ? 1 : 0",
                    workspace,
                )
            self.assertIn(
                f'resource "azurerm_role_assignment" "{identity}_acr_reader" {{\n'
                "  count                = var.enable_private_endpoints ? 1 : 0\n"
                "  scope                = var.container_registry_id\n"
                '  role_definition_name = "Reader"',
                workspace,
            )
        self.assertIn(
            'resource "time_sleep" "wait_for_managed_network_rbac" {\n'
            "  count           = var.enable_private_endpoints ? 1 : 0\n"
            '  create_duration = "120s"',
            workspace,
        )
        self.assertNotIn("scope                = var.rg_id", workspace)
        self.assertIn(
            'approval_contract = "target-scoped-approver-acr-reader-storage-data-v2"',
            workspace,
        )
        self.assertIn(
            "approval_scopes = jsonencode(sort([\n"
            "      var.container_registry_id,\n"
            "      var.key_vault_id,\n"
            "      var.storage_account_id\n"
            "    ]))",
            workspace,
        )
        for dependency in (
            "mlw_uai_storage_network_connection_approver",
            "mlw_uai_keyvault_network_connection_approver",
            "mlw_uai_acr_network_connection_approver",
            "mlw_uai_acr_reader",
            "mlw_system_storage_network_connection_approver",
            "mlw_system_keyvault_network_connection_approver",
            "mlw_system_acr_network_connection_approver",
            "mlw_system_acr_reader",
        ):
            self.assertIn(
                f"azurerm_role_assignment.{dependency}",
                workspace,
            )
        self.assertIn(
            "depends_on = [\n"
            "    azapi_update_resource.identity_based_system_datastores,\n"
            "    azurerm_private_endpoint.mlw_pe,\n"
            "    time_sleep.wait_for_managed_network_rbac\n"
            "  ]",
            workspace,
        )
        self.assertIn(
            "node_public_ip_enabled        = !var.enable_private_endpoints\n\n"
            "  identity {",
            workspace,
        )
        self.assertIn(
            "depends_on = [\n"
            "    azapi_update_resource.identity_based_system_datastores,\n"
            "    azurerm_private_endpoint.mlw_pe,\n"
            "    azapi_resource_action.provision_managed_network\n"
            "  ]",
            workspace,
        )
        self.assertIn(
            "public_network_access_enabled = !var.enable_private_endpoints",
            workspace,
        )
        self.assertNotIn("subnet_resource_id", workspace)
        self.assertIn(
            "node_public_ip_enabled        = !var.enable_private_endpoints",
            workspace,
        )

    def test_endpoint_deployments_use_supported_private_compute(self):
        online = (
            ROOT
            / "classical/aml-cli-v2/mlops/azureml/deploy/online/online-deployment.yml"
        ).read_text()
        self.assertIn("instance_type: Standard_D2ds_v5", online)
        self.assertNotIn("Standard_D4s_v5", online)

        private_online = (
            ROOT
            / "classical/aml-cli-v2/mlops/azureml/deploy/online/online-deployment-private.yml"
        ).read_text()
        self.assertIn("instance_type: Standard_D2ds_v5", private_online)
        self.assertNotIn("egress_public_network_access", private_online)
        self.assertIn("egress_public_network_access: enabled", online)

        online_pipeline = (
            ROOT
            / "classical/aml-cli-v2/mlops/devops-pipelines/deploy-online-endpoint-pipeline.yml"
        ).read_text()
        self.assertIn("online-deployment-private.yml", online_pipeline)
        self.assertIn("deployment_file: $(online_deployment_file)", online_pipeline)

        batch = (
            ROOT
            / "classical/aml-cli-v2/mlops/azureml/deploy/batch/batch-deployment.yml"
        ).read_text()
        self.assertIn("compute: azureml:cpu-cluster", batch)
        self.assertNotIn("compute: azureml:batch-cluster", batch)

        batch_pipeline = (
            ROOT
            / "classical/aml-cli-v2/mlops/devops-pipelines/deploy-batch-endpoint-pipeline.yml"
        ).read_text()
        self.assertNotIn(
            "templates/aml-cli-v2/create-compute.yml@mlops-templates",
            batch_pipeline,
        )
        self.assertNotIn("STANDARD_D4S_V5", batch_pipeline)
        self.assertIn("sample_request: azureml:taxi-data@latest", batch_pipeline)
        self.assertIn("request_type: uri_file", batch_pipeline)
        self.assertNotIn(
            "sample_request: classical/aml-cli-v2/data/taxi-batch.csv",
            batch_pipeline,
        )
        common = (ROOT / "config-infra-common.yml").read_text()
        self.assertNotIn("batch_compute_name", common)

    def test_mlflow_models_include_aml_monitoring_dependency(self):
        for source_name in ("train.py", "register.py"):
            source = (
                ROOT / "classical/aml-cli-v2/data-science/src" / source_name
            ).read_text()
            requirement_lines = [
                line.strip()
                for line in source.splitlines()
                if line.strip().startswith('"')
            ]
            mlflow_index = requirement_lines.index('"mlflow==2.22.4",')
            self.assertEqual(
                requirement_lines[mlflow_index + 1],
                '"azureml-ai-monitoring==1.0.0",',
            )
            self.assertEqual(
                source.count('"azureml-ai-monitoring==1.0.0"'),
                1,
            )

    def test_terraform_cli_uses_current_runtime_pin(self):
        common = (ROOT / "config-infra-common.yml").read_text()
        self.assertIn("terraform_version: 1.16.x", common)

    def test_no_live_azure_devops_identifiers_are_committed(self):
        terraform_sample = (
            ROOT / "infrastructure/terraform/terraform.tfvars.sample"
        )
        workspace_datastore = (
            ROOT
            / "classical/aml-cli-v2/mlops/azureml/datastores/workspaceblobstore.yml"
        )
        checked_paths = [
            ROOT / "config-infra-common.yml",
            *ENVIRONMENT_CONFIGS.values(),
            terraform_sample,
        ]
        for path in checked_paths:
            content = path.read_text()
            self.assertNotIn("Azure-ARM-Dev", content)
            self.assertNotIn("Azure-ARM-Test", content)
            self.assertNotIn("Azure-ARM-Prod", content)
            self.assertNotIn("00000000-0000-0000-0000-000000000000", content)

        sample = terraform_sample.read_text()
        self.assertIn('prefix         = "mlopsv2"', sample)
        self.assertIn('postfix        = "0001"', sample)
        self.assertNotIn('postfix        = "10001"', sample)
        self.assertFalse(
            workspace_datastore.exists(),
            "Do not commit a workspace-generated datastore account/container",
        )


if __name__ == "__main__":
    unittest.main()
