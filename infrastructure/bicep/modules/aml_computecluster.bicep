param location string
param computeClusterName string = 'cpu-cluster'
param workspaceName string
param vmSku string = 'STANDARD_D16S_V3'

resource amlci 'Microsoft.MachineLearningServices/workspaces/computes@2025-09-01' = {
  name: '${workspaceName}/${computeClusterName}'
  location: location
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: vmSku
      osType: 'Linux'
      scaleSettings: {
        maxNodeCount: 4
        minNodeCount: 0
      }
    }
  }
}
