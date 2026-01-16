param baseName string
param location string
param tags object

// Key Vault
// Note: enablePurgeProtection defaults to false but cannot be toggled after initial creation
resource kv 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: 'kv-${baseName}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      name: 'standard'
      family: 'A'
    }
    accessPolicies: []
    enableSoftDelete: true
  }

  tags: tags
}

output kvOut string = kv.id
