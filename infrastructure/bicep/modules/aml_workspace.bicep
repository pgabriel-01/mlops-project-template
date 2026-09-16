param baseName string
param location string
param stoacctid string
param kvid string
param appinsightid string
param crid string
param tags object
param managedIdentityId string
param managedIdentityPrincipalId string
param ciPrincipalObjectId string = ''
param enableNetworkIsolation bool = false
param computeSubnetId string = ''

// Extract resource IDs for RBAC assignments
var storageAccountName = split(stoacctid, '/')[8]
var keyVaultName = split(kvid, '/')[8]
var hasContainerRegistry = !empty(crid)
var containerRegistryName = hasContainerRegistry ? split(crid, '/')[8] : 'none'
var hasAppInsights = !empty(appinsightid)

// AML workspace with user-assigned managed identity
resource amls 'Microsoft.MachineLearningServices/workspaces@2025-06-01' = {
  name: 'mlw-${baseName}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  sku: {
    tier: 'Basic'
    name: 'Basic'
  }
  properties: {
    storageAccount: stoacctid
    keyVault: kvid
    applicationInsights: hasAppInsights ? appinsightid : null
    containerRegistry: hasContainerRegistry ? crid : null
    primaryUserAssignedIdentity: managedIdentityId
    systemDatastoresAuthMode: 'identity'  // Use managed identity for datastore auth instead of access keys
    publicNetworkAccess: enableNetworkIsolation ? 'Disabled' : 'Enabled'
    managedNetwork: enableNetworkIsolation ? {
      isolationMode: 'AllowInternetOutbound'
    } : null
    serverlessComputeSettings: enableNetworkIsolation ? {
      serverlessComputeCustomSubnet: computeSubnetId
      serverlessComputeNoPublicIP: true
    } : null
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

// Get existing container registry for RBAC assignments (only when CR is deployed)
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = if (hasContainerRegistry) {
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

resource workspaceMsiStorageQueueContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88') // Storage Queue Data Contributor
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource workspaceMsiStorageTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3') // Storage Table Data Contributor
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

// RBAC: Workspace MSI -> ACR Pull (only when container registry is deployed)
resource workspaceMsiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hasContainerRegistry) {
  name: guid(containerRegistry.id, managedIdentityPrincipalId, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Workspace MSI -> ACR Push (for image_build_compute to push built images)
resource workspaceMsiAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hasContainerRegistry) {
  name: guid(containerRegistry.id, managedIdentityPrincipalId, '8311e382-0749-4cb8-b61a-304f252e45ec')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec') // AcrPush
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: CI workload identity -> Storage Blob Data Contributor
resource ciStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(ciPrincipalObjectId)) {
  name: guid(storageAccount.id, ciPrincipalObjectId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: ciPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: CI workload identity -> workspace Contributor
resource ciWorkspaceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(ciPrincipalObjectId)) {
  name: guid(amls.id, ciPrincipalObjectId, 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  scope: amls
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c') // Contributor
    principalId: ciPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output amlsName string = amls.name
output amlsId string = amls.id
