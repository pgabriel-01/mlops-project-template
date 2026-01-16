param baseName string
param location string
param tags object

// Key Vault
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
    enablePurgeProtection: false  // Allow purging for destroy workflow
  }

  tags: tags
}

output kvOut string = kv.id
