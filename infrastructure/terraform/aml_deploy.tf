# Resource group

module "resource_group" {
  source = "./modules/resource-group"

  location = var.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  tags = local.tags
}

# Virtual Network (only created if private endpoints are enabled)

data "azurerm_virtual_network" "platform" {
  count = var.enable_private_endpoints ? 1 : 0

  name                = local.platform_virtual_network_name
  resource_group_name = local.platform_resource_group_name
}

module "vnet" {
  count  = var.enable_private_endpoints ? 1 : 0
  source = "./modules/vnet"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  vnet_address_space              = var.vnet_address_space
  training_subnet_address_prefix  = var.training_subnet_address_prefix
  endpoints_subnet_address_prefix = var.endpoints_subnet_address_prefix
  tags                            = local.tags
}

resource "azurerm_virtual_network_peering" "platform_to_workload" {
  count = var.enable_private_endpoints ? 1 : 0

  name                      = "peer-agents-to-workload"
  resource_group_name       = local.platform_resource_group_name
  virtual_network_name      = data.azurerm_virtual_network.platform[0].name
  remote_virtual_network_id = module.vnet[0].vnet_id
}

resource "azurerm_virtual_network_peering" "workload_to_platform" {
  count = var.enable_private_endpoints ? 1 : 0

  name                      = "peer-workload-to-agents"
  resource_group_name       = module.resource_group.name
  virtual_network_name      = module.vnet[0].vnet_name
  remote_virtual_network_id = data.azurerm_virtual_network.platform[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "workload_aml_zones_to_platform" {
  for_each = var.enable_private_endpoints ? {
    aml_api       = module.vnet[0].private_dns_zone_names.aml_api
    aml_notebooks = module.vnet[0].private_dns_zone_names.aml_notebooks
  } : {}

  name                  = "link-agents-${replace(each.value, ".", "_")}"
  resource_group_name   = module.resource_group.name
  private_dns_zone_name = each.value
  virtual_network_id    = data.azurerm_virtual_network.platform[0].id
  registration_enabled  = false
  tags                  = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "workload_service_zones_to_platform" {
  for_each = var.enable_private_endpoints ? {
    for key, name in module.vnet[0].private_dns_zone_names : key => name
    if !contains(["aml_api", "aml_notebooks", "blob"], key)
  } : {}

  name                  = "link-${each.key}-platform"
  resource_group_name   = module.resource_group.name
  private_dns_zone_name = each.value
  virtual_network_id    = data.azurerm_virtual_network.platform[0].id
  registration_enabled  = false
  tags                  = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "workload_blob_to_platform" {
  count = var.enable_private_endpoints ? 1 : 0

  name                  = "link-agents-privatelink_blob_core_windows_net"
  resource_group_name   = module.resource_group.name
  private_dns_zone_name = module.vnet[0].private_dns_zone_names.blob
  virtual_network_id    = data.azurerm_virtual_network.platform[0].id
  registration_enabled  = false
  tags                  = local.tags
}

import {
  for_each = var.enable_private_endpoints && var.import_existing_platform_connectivity ? {
    platform_to_workload = true
  } : {}

  to = azurerm_virtual_network_peering.platform_to_workload[0]
  id = "${data.azurerm_virtual_network.platform[0].id}/virtualNetworkPeerings/peer-agents-to-workload"
}

import {
  for_each = var.enable_private_endpoints && var.import_existing_platform_connectivity ? {
    workload_to_platform = true
  } : {}

  to = azurerm_virtual_network_peering.workload_to_platform[0]
  id = "${module.vnet[0].vnet_id}/virtualNetworkPeerings/peer-workload-to-agents"
}

import {
  for_each = var.enable_private_endpoints && var.import_existing_platform_connectivity ? {
    aml_api       = "privatelink.api.azureml.ms"
    aml_notebooks = "privatelink.notebooks.azure.net"
  } : {}

  to = azurerm_private_dns_zone_virtual_network_link.workload_aml_zones_to_platform[each.key]
  id = "${module.resource_group.id}/providers/Microsoft.Network/privateDnsZones/${each.value}/virtualNetworkLinks/link-agents-${replace(each.value, ".", "_")}"
}

import {
  for_each = var.enable_private_endpoints && var.import_existing_platform_connectivity ? {
    blob = true
  } : {}

  to = azurerm_private_dns_zone_virtual_network_link.workload_blob_to_platform[0]
  id = "${module.resource_group.id}/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net/virtualNetworkLinks/link-agents-privatelink_blob_core_windows_net"
}

# Azure Machine Learning workspace

module "aml_workspace" {
  source = "./modules/aml-workspace"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  storage_account_id      = module.storage_account_aml.id
  key_vault_id            = module.key_vault.id
  application_insights_id = module.application_insights.id
  container_registry_id   = module.container_registry.id

  enable_aml_computecluster = var.enable_aml_computecluster
  aml_compute_sku           = var.aml_compute_sku
  storage_account_name      = module.storage_account_aml.name

  cicd_principal_object_id = var.cicd_principal_object_id

  # Private endpoints configuration
  enable_private_endpoints          = var.enable_private_endpoints
  private_endpoint_subnet_id        = var.enable_private_endpoints ? module.vnet[0].endpoints_subnet_id : ""
  private_dns_zone_aml_api_id       = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.aml_api : ""
  private_dns_zone_aml_notebooks_id = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.aml_notebooks : ""

  tags = local.tags

  depends_on = [
    module.vnet
  ]
}

# Storage account

module "storage_account_aml" {
  source = "./modules/storage-account"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  hns_enabled                         = false
  firewall_bypass                     = ["AzureServices"]
  firewall_virtual_network_subnet_ids = var.enable_private_endpoints ? [module.vnet[0].training_subnet_id] : []

  # Private endpoints configuration
  enable_private_endpoints   = var.enable_private_endpoints
  private_endpoint_subnet_id = var.enable_private_endpoints ? module.vnet[0].endpoints_subnet_id : ""
  private_dns_zone_blob_id   = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.blob : ""
  private_dns_zone_file_id   = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.file : ""
  private_dns_zone_dfs_id    = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.dfs : ""
  private_dns_zone_queue_id  = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.queue : ""
  private_dns_zone_table_id  = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.table : ""

  tags = local.tags

  depends_on = [
    module.vnet
  ]
}

# Key vault

module "key_vault" {
  source = "./modules/key-vault"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  # Private endpoints configuration
  enable_private_endpoints            = var.enable_private_endpoints
  private_endpoint_subnet_id          = var.enable_private_endpoints ? module.vnet[0].endpoints_subnet_id : ""
  private_dns_zone_keyvault_id        = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.keyvault : ""
  firewall_virtual_network_subnet_ids = var.enable_private_endpoints ? [module.vnet[0].training_subnet_id] : []

  tags = local.tags
}

# Application insights

module "application_insights" {
  source = "./modules/application-insights"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  tags = local.tags
}

# Container registry

module "container_registry" {
  source = "./modules/container-registry"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix  = var.prefix
  postfix = local.resource_postfix
  env     = var.environment

  # Private endpoints configuration
  enable_private_endpoints            = var.enable_private_endpoints
  private_endpoint_subnet_id          = var.enable_private_endpoints ? module.vnet[0].endpoints_subnet_id : ""
  private_dns_zone_acr_id             = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_ids.acr : ""
  firewall_virtual_network_subnet_ids = var.enable_private_endpoints ? [module.vnet[0].training_subnet_id] : []

  tags = local.tags

  depends_on = [
    module.vnet
  ]
}

module "data_explorer" {
  source = "./modules/data-explorer"

  rg_name  = module.resource_group.name
  location = module.resource_group.location

  prefix            = var.prefix
  postfix           = local.resource_postfix
  env               = var.environment
  key_vault_id      = module.key_vault.id
  enable_monitoring = var.enable_monitoring

  tags = local.tags

  depends_on = [
    module.key_vault
  ]
}
