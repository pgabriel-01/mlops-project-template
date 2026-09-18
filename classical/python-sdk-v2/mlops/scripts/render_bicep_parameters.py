import argparse
import json
import os
from pathlib import Path

from project_config import load_config


PARAMETER_MAP = {
    "location": "location",
    "namespace": "prefix",
    "postfix": "postfix",
    "environment": "env",
    "aml_compute_sku": "amlComputeSku",
    "batch_compute_name": "imageBuildComputeName",
    "enable_monitoring": "enableMonitoring",
    "enable_container_registry": "enableContainerRegistry",
    "enable_compute_cluster": "enableComputeCluster",
    "enable_vnet": "enableVNet",
    "runner_hub_vnet_resource_id": "runnerHubVnetResourceId",
    "manage_runner_hub_to_workload_peering": "manageRunnerHubToWorkloadPeering",
    "enable_managed_online_endpoint": "enableManagedOnlineEndpoint",
    "online_mlflow_no_code": "onlineMlflowNoCode",
    "online_environment_name": "onlineEnvironmentName",
    "online_environment_version": "onlineEnvironmentVersion",
    "online_environment_image": "onlineEnvironmentImage",
    "online_endpoint_allow_key_vault_secrets": "onlineEndpointAllowKeyVaultSecrets",
    "enable_cmek": "enableCMEK",
    "enable_defender": "enableDefender",
    "project_number": "projectNumber",
    "enable_aml_registry": "enableAMLRegistry",
    "enable_ai_foundry": "enableAIFoundry",
    "enable_api_management": "enableAPIManagement",
    "kv_enable_purge_protection": "kvEnablePurgeProtection",
    "kv_soft_delete_retention_days": "kvSoftDeleteRetentionDays",
    "vnet_address_prefix": "vnetAddressPrefix",
    "default_subnet_prefix": "defaultSubnetPrefix",
    "compute_subnet_prefix": "computeSubnetPrefix",
    "private_endpoint_subnet_prefix": "peSubnetPrefix",
    "enable_dev_jumpbox": "enableDevJumpbox",
    "bastion_subnet_prefix": "bastionSubnetPrefix",
    "administration_subnet_prefix": "administrationSubnetPrefix",
    "dev_jumpbox_vm_size": "devJumpboxVmSize",
    "dev_jumpbox_ubuntu_image_version": "devJumpboxUbuntuImageVersion",
    "dev_jumpbox_azure_cli_version": "devJumpboxAzureCliVersion",
    "dev_jumpbox_azure_ml_extension_version": "devJumpboxAzureMlExtensionVersion",
    "dev_jumpbox_azure_ai_ml_version": "devJumpboxAzureAiMlVersion",
    "dev_jumpbox_azure_identity_version": "devJumpboxAzureIdentityVersion",
    "dev_jumpbox_shutdown_time": "devJumpboxShutdownTime",
    "dev_jumpbox_shutdown_timezone": "devJumpboxShutdownTimeZone",
    "dev_jumpbox_login_group_id": "devJumpboxLoginGroupId",
    "tag_cost_center": "tagCostCenter",
    "tag_managed_by": "tagManagedBy",
    "team_lead_group_id": "teamLeadGroupId",
    "data_scientist_group_id": "dataScientistGroupId",
    "ml_engineer_group_id": "mlEngineerGroupId",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_file", type=Path)
    parser.add_argument("output_file", type=Path)
    args = parser.parse_args()

    config = load_config(args.config_file)
    ci_principal_object_id = os.getenv("AZURE_PRINCIPAL_OBJECT_ID", "").strip()
    if not ci_principal_object_id:
        raise SystemExit("AZURE_PRINCIPAL_OBJECT_ID is required")
    parameters = {
        parameter: {"value": config[key]} for key, parameter in PARAMETER_MAP.items()
    }
    parameters["sharedPrivateDnsZoneResourceIds"] = {
        "value": json.loads(str(config["shared_private_dns_zone_resource_ids"]))
    }
    parameters["ciPrincipalObjectId"] = {"value": ci_principal_object_id}
    payload = {
        "$schema": (
            "https://schema.management.azure.com/schemas/"
            "2019-04-01/deploymentParameters.json#"
        ),
        "contentVersion": "1.0.0.0",
        "parameters": parameters,
    }
    args.output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
