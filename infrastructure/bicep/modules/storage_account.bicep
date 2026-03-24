param baseName string
param location string
param tags object
param enableNetworkIsolation bool = false
param allowedSubnetIds array = []

// Build VNet rules array for network ACLs
var virtualNetworkRules = [for subnetId in allowedSubnetIds: {
  id: subnetId
  action: 'Allow'
}]

// Storage Account
resource stoacct 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: 'st${baseName}'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    supportsHttpsTrafficOnly: true
    allowSharedKeyAccess: false  // Disable key-based authentication, use Entra ID (managed identity) instead
    networkRuleSet: enableNetworkIsolation ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: virtualNetworkRules
    } : {
      defaultAction: 'Allow'
    }
  }

  tags: tags
}

output stoacctOut string = stoacct.id
output stoacctName string = stoacct.name
