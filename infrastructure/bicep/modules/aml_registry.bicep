// Azure Machine Learning Registry — cross-workspace model/asset promotion
param baseName string
param location string
param tags object
param enablePublicAccess bool = true
param managedIdentityPrincipalId string = ''
param ciPrincipalObjectId string = ''

resource amlRegistry 'Microsoft.MachineLearningServices/registries@2024-04-01' = {
  name: 'reg-${baseName}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: enablePublicAccess ? 'Enabled' : 'Disabled'
    regionDetails: [
      {
        location: location
        storageAccountDetails: [
          {
            systemCreatedStorageAccount: {
              storageAccountType: 'Standard_LRS'
              allowBlobPublicAccess: false
            }
          }
        ]
        acrDetails: [
          {
            systemCreatedAcrAccount: {
              acrAccountSku: 'Premium'
            }
          }
        ]
      }
    ]
  }
}

// AzureML Registry User — allows workspace MI to pull assets from the registry
// Role ID: 1823dd4f-9b8c-4ab6-ab4e-7397a3684615
resource rbacMiRegistryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(managedIdentityPrincipalId)) {
  name: guid(amlRegistry.id, managedIdentityPrincipalId, '1823dd4f-9b8c-4ab6-ab4e-7397a3684615')
  scope: amlRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1823dd4f-9b8c-4ab6-ab4e-7397a3684615')
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// AzureML Registry User — allows the CI workload identity to push/pull assets
resource rbacCiRegistryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(ciPrincipalObjectId)) {
  name: guid(amlRegistry.id, ciPrincipalObjectId, '1823dd4f-9b8c-4ab6-ab4e-7397a3684615')
  scope: amlRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1823dd4f-9b8c-4ab6-ab4e-7397a3684615')
    principalId: ciPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output registryId string = amlRegistry.id
output registryName string = amlRegistry.name
