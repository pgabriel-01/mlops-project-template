param baseName string
param location string
param tags object
param vnetAddressPrefix string = '10.0.0.0/16'
param defaultSubnetPrefix string = '10.0.0.0/24'
param computeSubnetPrefix string = '10.0.1.0/24'
param privateEndpointSubnetPrefix string = '10.0.2.0/24'
param bastionSubnetPrefix string = '10.0.3.0/26'
param enableBastion bool = false

// NAT Gateway for outbound internet from aml-compute subnet
// Required for serverless compute image builds with no public IP
resource natGatewayPip 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-nat-${baseName}'
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
  name: 'nat-${baseName}'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIpAddresses: [
      { id: natGatewayPip.id }
    ]
    idleTimeoutInMinutes: 10
  }
  tags: tags
}

var coreSubnets = [
  {
    name: 'default'
    properties: {
      addressPrefix: defaultSubnetPrefix
      serviceEndpoints: [
        { service: 'Microsoft.KeyVault' }
        { service: 'Microsoft.Storage' }
      ]
    }
  }
  {
    name: 'aml-compute'
    properties: {
      addressPrefix: computeSubnetPrefix
      natGateway: {
        id: natGateway.id
      }
      serviceEndpoints: [
        { service: 'Microsoft.KeyVault' }
        { service: 'Microsoft.Storage' }
        { service: 'Microsoft.ContainerRegistry' }
      ]
    }
  }
  {
    name: 'private-endpoints'
    properties: {
      addressPrefix: privateEndpointSubnetPrefix
      privateEndpointNetworkPolicies: 'Disabled'
    }
  }
]

var bastionSubnet = [
  {
    name: 'AzureBastionSubnet'
    properties: {
      addressPrefix: bastionSubnetPrefix
    }
  }
]

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${baseName}'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: enableBastion ? concat(coreSubnets, bastionSubnet) : coreSubnets
  }
  tags: tags
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output defaultSubnetId string = vnet.properties.subnets[0].id
output computeSubnetId string = vnet.properties.subnets[1].id
output privateEndpointSubnetId string = vnet.properties.subnets[2].id
output bastionSubnetId string = enableBastion ? vnet.properties.subnets[3].id : ''
