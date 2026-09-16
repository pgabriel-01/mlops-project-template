// Generic private endpoint module — reusable for Storage, KV, ACR, AML Workspace
param location string
param tags object
param privateEndpointName string
param targetResourceId string
param groupId string  // e.g. 'blob', 'vault', 'registry', 'amlworkspace'
param subnetId string
param privateDnsZoneIds array = []

resource pe 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: privateEndpointName
  location: location
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointName
        properties: {
          privateLinkServiceId: targetResourceId
          groupIds: [
            groupId
          ]
        }
      }
    ]
  }
  tags: tags
}

// DNS zone group — links PE to private DNS zone for automatic DNS resolution
resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (!empty(privateDnsZoneIds)) {
  name: 'default'
  parent: pe
  properties: {
    privateDnsZoneConfigs: [for (privateDnsZoneId, index) in privateDnsZoneIds: {
      name: 'config-${index}'
      properties: {
        privateDnsZoneId: privateDnsZoneId
      }
    }]
  }
}

output privateEndpointId string = pe.id
