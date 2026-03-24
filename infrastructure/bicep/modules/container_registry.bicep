param baseName string
param location string
param tags object
param enableNetworkIsolation bool = false

// Premium SKU required for private endpoints; Standard when public
var skuName = enableNetworkIsolation ? 'Premium' : 'Standard'

resource cr 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: 'cr${baseName}'
  location: location
  sku: {
    name: skuName
  }

  properties: {
    adminUserEnabled: false
    publicNetworkAccess: enableNetworkIsolation ? 'Disabled' : 'Enabled'
    networkRuleBypassOptions: enableNetworkIsolation ? 'AzureServices' : 'None'
  }

  tags: tags
}

output crOut string = cr.id
output crName string = cr.name
