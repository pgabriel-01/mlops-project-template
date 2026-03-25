// AI Foundry Hub — deploys Azure AI Services account with project management enabled.
// This serves as the central hub for AI Foundry projects (GenAI, agents, prompt flow).
// Requires: enableAIFoundry feature flag in main.bicep

param baseName string
param location string
param tags object
param sku string = 'S0'
param enablePublicAccess bool = true
param storageAccountId string
param keyVaultId string
param managedIdentityId string

// AI Services account (AI Foundry Hub)
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'ais-${baseName}'
  location: location
  kind: 'AIServices'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  sku: {
    name: sku
  }
  properties: {
    customSubDomainName: 'ais-${baseName}'
    publicNetworkAccess: enablePublicAccess ? 'Enabled' : 'Disabled'
    disableLocalAuth: true
  }
  tags: tags
}

// AI Foundry Hub workspace (kind: Hub) — links AI Services to AML workspace ecosystem
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: 'aih-${baseName}'
  location: location
  kind: 'Hub'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    friendlyName: 'AI Foundry Hub - ${baseName}'
    description: 'AI Foundry Hub for GenAI workloads'
    storageAccount: storageAccountId
    keyVault: keyVaultId
    primaryUserAssignedIdentity: managedIdentityId
    publicNetworkAccess: enablePublicAccess ? 'Enabled' : 'Disabled'
  }
  tags: tags

  // Connect AI Services to the Hub
  resource aiServicesConnection 'connections@2024-10-01' = {
    name: 'ais-${baseName}-connection'
    properties: {
      category: 'AIServices'
      target: aiServices.properties.endpoint
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: aiServices.id
      }
    }
  }
}

output aiServicesId string = aiServices.id
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiHubId string = aiHub.id
output aiHubName string = aiHub.name
