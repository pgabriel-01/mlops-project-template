// Persona: Data Scientist — Workspace + compute + storage read, no KV admin
// Appropriate for data scientists who run experiments but don't manage infrastructure

param principalId string
param principalType string = 'Group'

param workspaceId string
param storageAccountId string
param keyVaultId string

// Extract resource names from IDs
var storageAccountName = split(storageAccountId, '/')[8]
var keyVaultName = split(keyVaultId, '/')[8]

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

// AzureML Data Scientist — run experiments, manage models, but not workspace settings
resource workspaceDataScientist 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workspace.id, principalId, 'f6c7c914-8db3-469d-8ca1-694a8f32e121-ds')
  scope: workspace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f6c7c914-8db3-469d-8ca1-694a8f32e121')
    principalId: principalId
    principalType: principalType
  }
}

// Storage Blob Data Reader — read training data, no write
resource storageBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
    principalId: principalId
    principalType: principalType
  }
}

// Key Vault Secrets User — read secrets but not manage them
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, '4633458b-17de-408a-b874-0445c86b69e6')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: principalId
    principalType: principalType
  }
}
