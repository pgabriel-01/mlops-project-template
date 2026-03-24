// AI Foundry Project — deploys a project workspace under an AI Foundry Hub.
// Each project provides isolated resources for a GenAI workload (prompt flow, agents, etc.)

param baseName string
param location string
param tags object
param aiHubId string
param managedIdentityId string

// AI Foundry Project workspace (kind: Project)
resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: 'aip-${baseName}'
  location: location
  kind: 'Project'
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
    friendlyName: 'AI Foundry Project - ${baseName}'
    description: 'Default AI Foundry Project for GenAI workloads'
    hubResourceId: aiHubId
    primaryUserAssignedIdentity: managedIdentityId
  }
  tags: tags
}

output aiProjectId string = aiProject.id
output aiProjectName string = aiProject.name
