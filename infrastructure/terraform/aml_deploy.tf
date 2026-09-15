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

data "azurerm_private_dns_zone" "platform_blob" {
  count = var.enable_private_endpoints ? 1 : 0

  name                = "privatelink.blob.core.windows.net"
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
  external_blob_private_dns_zone_id = (
    var.enable_private_endpoints ? data.azurerm_private_dns_zone.platform_blob[0].id : ""
  )

  tags = local.tags
}

resource "azurerm_virtual_network_peering" "platform_to_workload" {
  count = var.enable_private_endpoints ? 1 : 0

  name                      = "peer-platform-to-workload"
  resource_group_name       = local.platform_resource_group_name
  virtual_network_name      = data.azurerm_virtual_network.platform[0].name
  remote_virtual_network_id = module.vnet[0].vnet_id
}

resource "azurerm_virtual_network_peering" "workload_to_platform" {
  count = var.enable_private_endpoints ? 1 : 0

  name                      = "peer-workload-to-platform"
  resource_group_name       = module.resource_group.name
  virtual_network_name      = module.vnet[0].vnet_name
  remote_virtual_network_id = data.azurerm_virtual_network.platform[0].id
}

resource "azurerm_private_dns_zone_virtual_network_link" "workload_zones_to_platform" {
  for_each = var.enable_private_endpoints ? module.vnet[0].private_dns_zone_names : {}

  name                  = "link-${each.key}-platform"
  resource_group_name   = module.resource_group.name
  private_dns_zone_name = each.value
  virtual_network_id    = data.azurerm_virtual_network.platform[0].id
  registration_enabled  = false
  tags                  = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "platform_blob_to_workload" {
  count = var.enable_private_endpoints ? 1 : 0

  name                  = "link-blob-workload-${var.environment}"
  resource_group_name   = local.platform_resource_group_name
  private_dns_zone_name = data.azurerm_private_dns_zone.platform_blob[0].name
  virtual_network_id    = module.vnet[0].vnet_id
  registration_enabled  = false
  tags                  = local.tags
}

# Azure Machine Learning workspace

module "aml_workspace" {
  source = "./modules/aml-workspace"

  rg_name  = module.resource_group.name
  rg_id    = module.resource_group.id
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

  depends_on = [
    module.vnet
  ]
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
