param baseName string
param location string
param tags object
param enablePurgeProtection bool = false
param softDeleteRetentionDays int = 7
param enableNetworkIsolation bool = false
param allowedSubnetIds array = []

// Build VNet rules array for network ACLs
var virtualNetworkRules = [for subnetId in allowedSubnetIds: {
  id: subnetId
}]

// Key Vault — RBAC-authorized, idempotent with soft-delete handling
// Note: enablePurgeProtection cannot be disabled once enabled
resource kv 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: 'kv-${baseName}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      name: 'standard'
      family: 'A'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionDays
    enablePurgeProtection: enablePurgeProtection ? true : null
    networkAcls: enableNetworkIsolation ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: virtualNetworkRules
    } : {
      defaultAction: 'Allow'
    }
  }

  tags: tags
}

output kvOut string = kv.id
output kvName string = kv.name
