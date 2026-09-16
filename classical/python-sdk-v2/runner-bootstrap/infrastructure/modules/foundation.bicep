param aksName string
param location string
param logRetentionDays int
param tags object

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-${aksName}'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
  tags: tags
}

resource natGateway 'Microsoft.Network/natGateways@2024-05-01' = {
  name: 'nat-${aksName}'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 10
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
  tags: tags
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${aksName}'
  location: location
  properties: {
    retentionInDays: logRetentionDays
    sku: {
      name: 'PerGB2018'
    }
  }
  tags: tags
}

resource controlPlaneIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${aksName}-control-plane'
  location: location
  tags: tags
}

output natGatewayId string = natGateway.id
output natPublicIpAddress string = natPublicIp.properties.ipAddress
output logAnalyticsWorkspaceId string = logAnalytics.id
output controlPlaneIdentityId string = controlPlaneIdentity.id
output controlPlaneIdentityPrincipalId string = controlPlaneIdentity.properties.principalId
output controlPlaneIdentityClientId string = controlPlaneIdentity.properties.clientId
