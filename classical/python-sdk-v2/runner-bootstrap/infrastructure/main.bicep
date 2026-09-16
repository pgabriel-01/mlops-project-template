targetScope = 'subscription'

@description('Azure region for the dedicated runner infrastructure.')
param location string = 'eastus2'

@description('Resource group for the dedicated AKS runner infrastructure.')
param resourceGroupName string = 'rg-mlops-arc-dev-eus2-001'

@description('Existing hub VNet resource group.')
param hubVnetResourceGroupName string = 'rg-mlops-hub-dev-eus2-001'

@description('Existing hub VNet name.')
param hubVnetName string = 'vnet-mlops-hub-dev-eus2-001'

@description('Dedicated, nondelegated subnet name for AKS nodes.')
param runnerSubnetName string = 'snet-github-runners'

@description('Dedicated runner subnet CIDR. This must not overlap an existing subnet.')
param runnerSubnetPrefix string = '10.240.2.0/24'

@description('Private AKS cluster name.')
param aksName string = 'aks-mlops-arc-dev-eus2-001'

@description('AKS system node VM size. Keep this quota-checked and cost bounded.')
param nodeVmSize string = 'Standard_D2ads_v6'

@minValue(1)
@maxValue(3)
@description('Fixed system node count. ARC runner pods scale separately.')
param systemNodeCount int = 2

@description('AKS Kubernetes version. Empty lets AKS select the current default.')
param kubernetesVersion string = ''

@minValue(7)
@maxValue(90)
@description('Retention for AKS control-plane and Container Insights logs.')
param logRetentionDays int = 30

param tags object = {
  Environment: 'dev'
  ManagedBy: 'bicep'
  Purpose: 'github-actions-arc'
  Repository: 'template-example'
}

resource runnerRg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module foundation './modules/foundation.bicep' = {
  name: 'runner-foundation'
  scope: resourceGroup(runnerRg.name)
  params: {
    aksName: aksName
    location: location
    logRetentionDays: logRetentionDays
    tags: tags
  }
}

module subnet './modules/runner_subnet.bicep' = {
  name: 'runner-subnet'
  scope: resourceGroup(hubVnetResourceGroupName)
  params: {
    controlPlaneIdentityPrincipalId: foundation.outputs.controlPlaneIdentityPrincipalId
    hubVnetName: hubVnetName
    natGatewayId: foundation.outputs.natGatewayId
    runnerSubnetName: runnerSubnetName
    runnerSubnetPrefix: runnerSubnetPrefix
  }
}

module cluster './modules/aks.bicep' = {
  name: 'runner-aks'
  scope: resourceGroup(runnerRg.name)
  params: {
    aksName: aksName
    controlPlaneIdentityId: foundation.outputs.controlPlaneIdentityId
    kubernetesVersion: kubernetesVersion
    location: location
    logAnalyticsWorkspaceId: foundation.outputs.logAnalyticsWorkspaceId
    nodeVmSize: nodeVmSize
    runnerSubnetId: subnet.outputs.runnerSubnetId
    systemNodeCount: systemNodeCount
    tags: tags
  }
}

output aksName string = cluster.outputs.aksName
output resourceGroupName string = runnerRg.name
output runnerSubnetId string = subnet.outputs.runnerSubnetId
output natPublicIpAddress string = foundation.outputs.natPublicIpAddress
output logAnalyticsWorkspaceId string = foundation.outputs.logAnalyticsWorkspaceId
output controlPlaneIdentityId string = foundation.outputs.controlPlaneIdentityId
output controlPlaneIdentityClientId string = foundation.outputs.controlPlaneIdentityClientId
output controlPlaneSubnetRoleAssignmentId string = subnet.outputs.controlPlaneSubnetRoleAssignmentId
