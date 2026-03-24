param location string
param computeClusterName string = 'cpu-cluster'
param workspaceName string
param vmSku string = 'STANDARD_D2S_V3'
param managedIdentityId string
param subnetId string = ''

resource amlci 'Microsoft.MachineLearningServices/workspaces/computes@2025-09-01' = {
  name: '${workspaceName}/${computeClusterName}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: vmSku
      osType: 'Linux'
      scaleSettings: {
        maxNodeCount: 4
        minNodeCount: 0
      }
      subnet: !empty(subnetId) ? {
        id: subnetId
      } : null
    }
  }
}
