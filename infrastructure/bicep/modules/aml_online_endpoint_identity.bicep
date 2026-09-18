param baseName string
param location string
param tags object
param storageAccountId string
param containerRegistryId string
param keyVaultId string
param allowKeyVaultSecrets bool = false
param ciPrincipalObjectId string = ''

var storageBlobDataReaderRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // Storage Blob Data Reader
)
var acrPullRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
)
var keyVaultSecretsUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)
var managedIdentityOperatorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'f1a07417-d97a-45cb-824c-7a7467783830'
)
resource endpointIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-online-${baseName}'
  location: location
  tags: union(tags, {
    Workload: 'managed-online-endpoint'
  })
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: split(storageAccountId, '/')[8]
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: split(containerRegistryId, '/')[8]
}

resource keyVault 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: split(keyVaultId, '/')[8]
}

resource endpointStorageReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, endpointIdentity.id, storageBlobDataReaderRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: storageBlobDataReaderRoleId
    principalId: endpointIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource endpointAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, endpointIdentity.id, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: endpointIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource endpointKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (allowKeyVaultSecrets) {
  name: guid(keyVault.id, endpointIdentity.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: endpointIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource ciManagedIdentityOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(ciPrincipalObjectId)) {
  name: guid(endpointIdentity.id, ciPrincipalObjectId, managedIdentityOperatorRoleId)
  scope: endpointIdentity
  properties: {
    roleDefinitionId: managedIdentityOperatorRoleId
    principalId: ciPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output identityId string = endpointIdentity.id
output identityName string = endpointIdentity.name
output identityClientId string = endpointIdentity.properties.clientId
output identityPrincipalId string = endpointIdentity.properties.principalId
