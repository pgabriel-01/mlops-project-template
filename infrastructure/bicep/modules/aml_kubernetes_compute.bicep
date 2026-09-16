param workspaceName string
param location string
param computeName string
param clusterResourceId string
param namespace string
param identityId string
param extensionPrincipalId string
param extensionReleaseTrain string
param instanceTypeName string
param cpuRequest string
param cpuLimit string
param memoryRequest string
param memoryLimit string

resource workspace 'Microsoft.MachineLearningServices/workspaces@2025-06-01' existing = {
  name: workspaceName
}

resource kubernetesCompute 'Microsoft.MachineLearningServices/workspaces/computes@2025-06-01' = {
  name: computeName
  parent: workspace
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    computeLocation: location
    computeType: 'Kubernetes'
    description: 'Private AKS inference compute isolated from system and ARC runner capacity.'
    disableLocalAuth: true
    resourceId: clusterResourceId
    properties: {
      defaultInstanceType: instanceTypeName
      extensionInstanceReleaseTrain: extensionReleaseTrain
      extensionPrincipalId: extensionPrincipalId
      instanceTypes: {
        '${instanceTypeName}': {
          nodeSelector: {
            'ml.azure.com/inference': 'true'
          }
          resources: {
            limits: {
              cpu: cpuLimit
              memory: memoryLimit
            }
            requests: {
              cpu: cpuRequest
              memory: memoryRequest
            }
          }
        }
      }
      namespace: namespace
    }
  }
}

output computeName string = kubernetesCompute.name
output computeId string = kubernetesCompute.id

