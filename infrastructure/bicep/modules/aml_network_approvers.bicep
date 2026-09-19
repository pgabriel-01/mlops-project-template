param managedIdentityPrincipalId string
param storageAccountId string
param keyVaultId string
param containerRegistryId string = ''
param workspaceId string

var networkConnectionApproverRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b556d68e-0be0-4f35-a333-ad7ee1ce17ea' // Azure AI Enterprise Network Connection Approver
)
var hasContainerRegistry = !empty(containerRegistryId)
var storageAccountName = split(storageAccountId, '/')[8]
var keyVaultName = split(keyVaultId, '/')[8]
var containerRegistryName = hasContainerRegistry ? split(containerRegistryId, '/')[8] : 'none'
var workspaceName = split(workspaceId, '/')[8]

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: storageAccountName
}

resource keyVault 'Microsoft.KeyVault/vaults@2025-05-01' existing = {
  name: keyVaultName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = if (hasContainerRegistry) {
  name: containerRegistryName
}

resource workspace 'Microsoft.MachineLearningServices/workspaces@2026-05-01' existing = {
  name: workspaceName
}

resource storageApprover 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, networkConnectionApproverRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: networkConnectionApproverRoleId
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultApprover 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentityPrincipalId, networkConnectionApproverRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: networkConnectionApproverRoleId
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource containerRegistryApprover 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hasContainerRegistry) {
  name: guid(containerRegistry.id, managedIdentityPrincipalId, networkConnectionApproverRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: networkConnectionApproverRoleId
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource containerRegistryReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (hasContainerRegistry) {
  name: guid(containerRegistry.id, managedIdentityPrincipalId, 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'acdd72a7-3385-48ef-bd42-f606fba81ae7' // Reader
    )
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource workspaceApprover 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workspace.id, managedIdentityPrincipalId, networkConnectionApproverRoleId)
  scope: workspace
  properties: {
    roleDefinitionId: networkConnectionApproverRoleId
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output storageRoleAssignmentId string = storageApprover.id
output keyVaultRoleAssignmentId string = keyVaultApprover.id
output containerRegistryRoleAssignmentId string = hasContainerRegistry ? containerRegistryApprover!.id : ''
output containerRegistryReaderRoleAssignmentId string = hasContainerRegistry ? containerRegistryReader!.id : ''
output workspaceRoleAssignmentId string = workspaceApprover.id
