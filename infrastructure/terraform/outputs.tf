output "resource_group_name" {
  value       = module.resource_group.name
  description = "Name of the deployed project resource group"
}

output "aml_workspace_name" {
  value       = module.aml_workspace.name
  description = "Name of the deployed Azure Machine Learning workspace"
}

output "storage_account_name" {
  value       = module.storage_account_aml.name
  description = "Name of the Azure Machine Learning storage account"
}

output "container_registry_name" {
  value       = module.container_registry.name
  description = "Name of the Azure Machine Learning container registry"
}

output "training_compute_name" {
  value       = module.aml_workspace.training_compute_name
  description = "Name of the Terraform-managed training compute cluster"
}

output "aml_workspace_identity_principal_id" {
  value       = module.aml_workspace.user_assigned_identity_principal_id
  description = "Principal ID of the workspace user-assigned managed identity"
}
