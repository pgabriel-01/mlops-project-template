param baseName string
param location string
param stoacctid string
param kvid string
param appinsightid string
param crid string
param tags object
param managedIdentityId string
param managedIdentityPrincipalId string
param adoServicePrincipalId string = ''

// Extract resource IDs for RBAC assignments
var storageAccountName = split(stoacctid, '/')[8]
var keyVaultName = split(kvid, '/')[8]
var containerRegistryName = split(crid, '/')[8]

// AML workspace with user-assigned managed identity
resource amls 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: 'mlw-${baseName}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  sku: {
    tier: 'basic'
    name: 'basic'
  }
  properties: {
    storageAccount: stoacctid
    keyVault: kvid
    applicationInsights: appinsightid
    containerRegistry: crid
    primaryUserAssignedIdentity: managedIdentityId
    systemDatastoresAuthMode: 'identity'  // Use managed identity for datastore auth instead of access keys
    publicNetworkAccess: 'Enabled'
    imageBuildCompute: 'cpu-cluster'
    v1LegacyMode: false
    encryption: {
      status: 'Disabled'
      keyVaultProperties: {
        keyIdentifier: ''
        keyVaultArmId: ''
      }
    }
  }

  tags: tags
}

// Get existing storage account for RBAC assignments
resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: storageAccountName
}

// Get existing key vault for RBAC assignments
resource keyVault 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

// Get existing container registry for RBAC assignments
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: containerRegistryName
}

// RBAC: Workspace MSI -> Storage Blob Data Contributor
resource workspaceMsiStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Workspace MSI -> Storage Account Contributor
resource workspaceMsiStorageAccountContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, '17d1049b-9a84-46fb-8f53-869881c3d3ab')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '17d1049b-9a84-46fb-8f53-869881c3d3ab') // Storage Account Contributor
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Workspace MSI -> Key Vault Administrator
resource workspaceMsiKeyVaultAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentityPrincipalId, '00482a5a-887f-4fb3-b363-3b7fe8e74483')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '00482a5a-887f-4fb3-b363-3b7fe8e74483') // Key Vault Administrator
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Workspace MSI -> ACR Pull
resource workspaceMsiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, managedIdentityPrincipalId, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: ADO Service Principal -> Storage Blob Data Reader (for data registration)
resource adoSpStorageBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adoServicePrincipalId)) {
  name: guid(storageAccount.id, adoServicePrincipalId, '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1') // Storage Blob Data Reader
    principalId: adoServicePrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: ADO Service Principal -> Storage Blob Data Contributor (for data registration)
resource adoSpStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adoServicePrincipalId)) {
  name: guid(storageAccount.id, adoServicePrincipalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: adoServicePrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: ADO Service Principal -> AzureML Workspace Contributor (for model registration)
resource adoSpWorkspaceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adoServicePrincipalId)) {
  name: guid(amls.id, adoServicePrincipalId, 'f6c7c914-8db3-469d-8ca1-694a8f32e121')
  scope: amls
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f6c7c914-8db3-469d-8ca1-694a8f32e121') // AzureML Compute Operator
    principalId: adoServicePrincipalId
    principalType: 'ServicePrincipal'
  }
}

output amlsName string = amls.name
output amlsId string = amls.id
