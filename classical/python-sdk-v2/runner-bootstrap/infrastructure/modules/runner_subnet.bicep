param hubVnetName string
param controlPlaneIdentityPrincipalId string
param natGatewayId string
param runnerSubnetName string
param runnerSubnetPrefix string

resource hubVnet 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: hubVnetName
}

resource runnerSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  name: runnerSubnetName
  parent: hubVnet
  properties: {
    addressPrefix: runnerSubnetPrefix
    natGateway: {
      id: natGatewayId
    }
    privateEndpointNetworkPolicies: 'Enabled'
    privateLinkServiceNetworkPolicies: 'Enabled'
  }
}

var networkContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4d97b98b-1d4f-4787-a291-c67834d212e7'
)

resource controlPlaneSubnetRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    runnerSubnet.id,
    controlPlaneIdentityPrincipalId,
    networkContributorRoleDefinitionId
  )
  scope: runnerSubnet
  properties: {
    principalId: controlPlaneIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: networkContributorRoleDefinitionId
  }
}

output runnerSubnetId string = runnerSubnet.id
output controlPlaneSubnetRoleAssignmentId string = controlPlaneSubnetRole.id
