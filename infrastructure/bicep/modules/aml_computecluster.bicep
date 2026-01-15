param location string
param computeClusterName string = 'cpu-cluster'
param workspaceName string

resource amlci 'Microsoft.MachineLearningServices/workspaces/computes@2025-09-01' = {
  name: '${workspaceName}/${computeClusterName}'
  location: location
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: 'STANDARD_DS12_V2'
      subnet: json('null')
      osType: 'Linux'
      scaleSettings: {
        maxNodeCount: 4
        minNodeCount: 0
      }
    }
  }
}
