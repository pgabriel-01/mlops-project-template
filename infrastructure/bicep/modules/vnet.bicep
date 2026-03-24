param baseName string
param location string
param tags object
param vnetAddressPrefix string = '10.0.0.0/16'
param defaultSubnetPrefix string = '10.0.0.0/24'
param computeSubnetPrefix string = '10.0.1.0/24'
param privateEndpointSubnetPrefix string = '10.0.2.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${baseName}'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'default'
        properties: {
          addressPrefix: defaultSubnetPrefix
        }
      }
      {
        name: 'aml-compute'
        properties: {
          addressPrefix: computeSubnetPrefix
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
  }
  tags: tags
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output defaultSubnetId string = vnet.properties.subnets[0].id
output computeSubnetId string = vnet.properties.subnets[1].id
output privateEndpointSubnetId string = vnet.properties.subnets[2].id
