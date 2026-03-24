// Seeding Key Vault — pre-existing KV that holds SP credentials and secrets
// Pipeline fetches creds at runtime instead of relying on service connection alone
// Supports firewall with temporary build agent IP whitelisting
param baseName string
param location string
param tags object
param enableNetworkIsolation bool = false

resource seedKv 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: 'kvseed-${baseName}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      name: 'standard'
      family: 'A'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: enableNetworkIsolation ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      // IP rules are managed dynamically by the pipeline (whitelist/cleanup pattern)
      ipRules: []
      virtualNetworkRules: []
    } : {
      defaultAction: 'Allow'
    }
  }
  tags: tags
}

output seedKvName string = seedKv.name
output seedKvId string = seedKv.id
