param baseName string
param location string
param tags object
param oidcIssuerUrl string
param namespace string
param serviceAccountName string
param storageAccountId string
param containerRegistryId string
param workspaceManagedIdentityPrincipalId string

var acrPullRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)
var storageBlobDataReaderRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
)
var managedIdentityOperatorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'f1a07417-d97a-45cb-824c-7a7467783830'
)

resource inferenceIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-${baseName}-inference'
  location: location
  tags: tags
}

resource workloadFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'aks-${namespace}-${serviceAccountName}'
  parent: inferenceIdentity
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: oidcIssuerUrl
    subject: 'system:serviceaccount:${namespace}:${serviceAccountName}'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: last(split(storageAccountId, '/'))
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: last(split(containerRegistryId, '/'))
}

resource inferenceStorageReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, inferenceIdentity.id, storageBlobDataReaderRoleId)
  scope: storage
  properties: {
    principalId: inferenceIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobDataReaderRoleId
  }
}

resource inferenceAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, inferenceIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: inferenceIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleId
  }
}

resource workspaceIdentityOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(inferenceIdentity.id, workspaceManagedIdentityPrincipalId, managedIdentityOperatorRoleId)
  scope: inferenceIdentity
  properties: {
    principalId: workspaceManagedIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: managedIdentityOperatorRoleId
  }
}

output identityId string = inferenceIdentity.id
output identityPrincipalId string = inferenceIdentity.properties.principalId
output identityClientId string = inferenceIdentity.properties.clientId
