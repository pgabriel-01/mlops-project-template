output "vnet_id" {
  value       = azurerm_virtual_network.vnet.id
  description = "The ID of the Virtual Network"
}

output "vnet_name" {
  value       = azurerm_virtual_network.vnet.name
  description = "The name of the Virtual Network"
}

output "training_subnet_id" {
  value       = azurerm_subnet.training.id
  description = "The ID of the training subnet"
}

output "endpoints_subnet_id" {
  value       = azurerm_subnet.endpoints.id
  description = "The ID of the private endpoints subnet"
}

output "training_subnet_name" {
  value       = azurerm_subnet.training.name
  description = "The name of the training subnet"
}

output "endpoints_subnet_name" {
  value       = azurerm_subnet.endpoints.name
  description = "The name of the private endpoints subnet"
}

output "private_dns_zone_ids" {
  value = {
    aml_api       = azurerm_private_dns_zone.aml_api.id
    aml_notebooks = azurerm_private_dns_zone.aml_notebooks.id
    blob          = var.external_blob_private_dns_zone_id != "" ? var.external_blob_private_dns_zone_id : azurerm_private_dns_zone.blob[0].id
    file          = azurerm_private_dns_zone.file.id
    dfs           = azurerm_private_dns_zone.dfs.id
    keyvault      = azurerm_private_dns_zone.keyvault.id
    acr           = azurerm_private_dns_zone.acr.id
  }
  description = "Map of private DNS zone IDs"
}

output "private_dns_zone_names" {
  value = {
    aml_api       = azurerm_private_dns_zone.aml_api.name
    aml_notebooks = azurerm_private_dns_zone.aml_notebooks.name
    file          = azurerm_private_dns_zone.file.name
    dfs           = azurerm_private_dns_zone.dfs.name
    keyvault      = azurerm_private_dns_zone.keyvault.name
    acr           = azurerm_private_dns_zone.acr.name
  }
  description = "Private DNS zone names created for workload services"
}

output "nsg_id" {
  value       = azurerm_network_security_group.training.id
  description = "The ID of the Network Security Group for training subnet"
}
