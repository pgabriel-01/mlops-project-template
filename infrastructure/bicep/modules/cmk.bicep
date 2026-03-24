// Customer Managed Key — creates a KV key and Disk Encryption Set for CMEK scenarios.
// The Key Vault must have purge-protection enabled (enforced via enablePurgeProtection param on kv module).

param baseName string
param location string
param tags object
param keyVaultId string
param managedIdentityPrincipalId string

// Extract Key Vault name from resource ID
var keyVaultName = last(split(keyVaultId, '/'))

// Reference existing Key Vault
resource kv 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

// Grant the managed identity Key Vault Crypto Officer so it can wrap/unwrap keys
resource kvCryptoOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, managedIdentityPrincipalId, 'Key Vault Crypto Officer')
  scope: kv
  properties: {
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '14b46e9e-c2b7-41b4-b07b-48a6ebf60603')
  }
}

// Encryption key for CMEK
resource cmkKey 'Microsoft.KeyVault/vaults/keys@2025-05-01' = {
  parent: kv
  name: 'cmk-${baseName}'
  properties: {
    kty: 'RSA'
    keySize: 2048
    keyOps: [
      'wrapKey'
      'unwrapKey'
    ]
  }
  dependsOn: [
    kvCryptoOfficer
  ]
  tags: tags
}

// Disk Encryption Set — used by compute and storage for CMEK
resource des 'Microsoft.Compute/diskEncryptionSets@2024-07-01' = {
  name: 'des-${baseName}'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    activeKey: {
      sourceVault: {
        id: kv.id
      }
      keyUrl: cmkKey.properties.keyUriWithVersion
    }
    encryptionType: 'EncryptionAtRestWithCustomerKey'
    rotationToLatestKeyVersionEnabled: true
  }
  tags: tags
}

// Grant the DES system identity Key Vault Crypto Service Encryption User
// so it can wrap/unwrap using the key
resource desCryptoUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, des.id, 'Key Vault Crypto Service Encryption User')
  scope: kv
  properties: {
    principalId: des.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'e147488a-f6f5-4113-8e2d-b22465e65bf6')
  }
}

output keyId string = cmkKey.properties.keyUriWithVersion
output diskEncryptionSetId string = des.id
