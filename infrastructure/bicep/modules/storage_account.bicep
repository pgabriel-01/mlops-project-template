param baseName string
param location string
param tags object

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
  }

  tags: tags
}

output stoacctOut string = stoacct.id
