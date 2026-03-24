// Private DNS Zones for private link resolution
param tags object
param vnetId string

// Use environment() suffixes for cloud-agnostic DNS zone names
var storageSuffix = environment().suffixes.storage  // e.g. core.windows.net
var dnsZones = [
  'privatelink.blob.${storageSuffix}'
  'privatelink.vaultcore.azure.net'
  'privatelink.azurecr.io'
  'privatelink.api.azureml.ms'
  'privatelink.notebooks.azure.net'
  'privatelink.file.${storageSuffix}'
  'privatelink.dfs.${storageSuffix}'
]

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = [for zone in dnsZones: {
  name: zone
  location: 'global'
  tags: tags
}]

// Link each DNS zone to the VNet
resource vnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [for (zone, i) in dnsZones: {
  name: 'link-${uniqueString(vnetId)}'
  parent: privateDnsZone[i]
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    registrationEnabled: false
  }
  tags: tags
}]

output blobDnsZoneId string = privateDnsZone[0].id
output kvDnsZoneId string = privateDnsZone[1].id
output acrDnsZoneId string = privateDnsZone[2].id
output amlDnsZoneId string = privateDnsZone[3].id
output notebookDnsZoneId string = privateDnsZone[4].id
output fileDnsZoneId string = privateDnsZone[5].id
output dfsDnsZoneId string = privateDnsZone[6].id
