// Persona: Team Lead — Full access to workspace, storage, KV, and compute
// Assigns roles needed for a team lead / project owner to all MLOps resources

param principalId string
param principalType string = 'Group' // 'Group' for Entra ID groups, 'User' for individual users

param workspaceId string
param storageAccountId string
param keyVaultId string
param containerRegistryId string = ''

// Extract resource names from IDs
var storageAccountName = split(storageAccountId, '/')[8]
var keyVaultName = split(keyVaultId, '/')[8]
var hasContainerRegistry = !empty(containerRegistryId)
var containerRegistryName = hasContainerRegistry ? split(containerRegistryId, '/')[8] : 'none'

// Reference existing resources
resource workspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' existing = {
  name: split(workspaceId, '/')[8]
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: storageAccountName
}

resource keyVault 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = if (hasContainerRegistry) {
  name: containerRegistryName
}

// AzureML Workspace Contributor
resource workspaceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workspace.id, principalId, 'f6c7c914-8db3-469d-8ca1-694a8f32e121')
  scope: workspace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f6c7c914-8db3-469d-8ca1-694a8f32e121')
    principalId: principalId
    principalType: principalType
  }
}

// Storage Blob Data Contributor
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: principalId
    principalType: principalType
  }
}

// Key Vault Administrator
resource kvAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, '00482a5a-887f-4fb3-b363-3b7fe8e74483')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '00482a5a-887f-4fb3-b363-3b7fe8e74483')
    principalId: principalId
    principalType: principalType
  }
}

// AcrPush (includes Pull)
resource acrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hasContainerRegistry) {
  name: guid(containerRegistry.id, principalId, '8311e382-0749-4cb8-b61a-304f252e45ec')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec')
    principalId: principalId
    principalType: principalType
  }
}
