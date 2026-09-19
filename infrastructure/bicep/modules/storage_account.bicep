@minLength(1)
param baseName string
param location string
param tags object
param enableNetworkIsolation bool = false
param allowedSubnetIds array = []
param enableDeploymentLocks bool = false
param ciPrincipalObjectId string = ''

// Build VNet rules array for network ACLs
var virtualNetworkRules = [for subnetId in allowedSubnetIds: {
  id: subnetId
  action: 'Allow'
}]

// Storage Account
resource stoacct 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: 'st${baseName}'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false  // Disable key-based authentication, use Entra ID (managed identity) instead
    networkAcls: enableNetworkIsolation ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      virtualNetworkRules: virtualNetworkRules
    } : {
      defaultAction: 'Allow'
    }
  }

  tags: tags
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = if (enableDeploymentLocks) {
  parent: stoacct
  name: 'default'
}

resource deploymentLocks 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = if (enableDeploymentLocks) {
  parent: blobService
  name: 'deployment-locks'
  properties: {
    publicAccess: 'None'
  }
}

resource ciDeploymentLockContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableDeploymentLocks && !empty(ciPrincipalObjectId)) {
  name: guid(deploymentLocks.id, ciPrincipalObjectId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: deploymentLocks
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalId: ciPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output stoacctOut string = stoacct.id
output stoacctName string = stoacct.name
output deploymentLockContainerName string = enableDeploymentLocks ? deploymentLocks.name : ''
