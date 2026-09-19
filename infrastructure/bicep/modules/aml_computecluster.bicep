param location string
param computeClusterName string = 'cpu-cluster'
param workspaceName string
param vmSku string = 'STANDARD_D16S_V3'
param managedIdentityId string
param subnetId string = ''
param workspaceManagedNetworkEnabled bool = false

var effectiveSubnetId = workspaceManagedNetworkEnabled ? '' : subnetId

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
    properties: union({
      vmSize: vmSku
      osType: 'Linux'
      enableNodePublicIp: workspaceManagedNetworkEnabled ? false : empty(effectiveSubnetId)
      scaleSettings: {
        maxNodeCount: 4
        minNodeCount: 0
      }
    }, !empty(effectiveSubnetId) ? {
      subnet: {
        id: effectiveSubnetId
      }
    } : {})
  }
}
