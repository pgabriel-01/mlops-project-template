// Private DNS Zones for private link resolution
param tags object
param vnetId string
param runnerHubVnetId string = ''
param sharedPrivateDnsZoneResourceIds object = {}

// Use environment() suffixes for cloud-agnostic DNS zone names
var storageSuffix = environment().suffixes.storage  // e.g. core.windows.net
var dnsZones = [
  'privatelink.blob.${storageSuffix}'
  'privatelink.file.${storageSuffix}'
  'privatelink.queue.${storageSuffix}'
  'privatelink.table.${storageSuffix}'
  'privatelink.dfs.${storageSuffix}'
  'privatelink.vaultcore.azure.net'
  'privatelink.azurecr.io'
  'privatelink.api.azureml.ms'
  'privatelink.notebooks.azure.net'
]
var managedDnsZones = filter(
  dnsZones,
  zone => !contains(sharedPrivateDnsZoneResourceIds, zone)
)
var privateDnsZoneIds = [
  for zone in dnsZones: contains(sharedPrivateDnsZoneResourceIds, zone)
    ? string(sharedPrivateDnsZoneResourceIds[zone])
    : resourceId('Microsoft.Network/privateDnsZones', zone)
]
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = [for zone in managedDnsZones: {
  name: zone
  location: 'global'
  tags: tags
}]

// The workload VNet is linked to every selected zone. Shared zones are reused
// directly so private endpoint records remain visible from the runner hub.
module vnetLink './private_dns_zone_vnet_link.bicep' = [for zoneId in privateDnsZoneIds: {
  name: 'dns-workload-link-${uniqueString(zoneId, vnetId)}'
  scope: resourceGroup(split(zoneId, '/')[2], split(zoneId, '/')[4])
  params: {
    privateDnsZoneName: split(zoneId, '/')[8]
    vnetId: vnetId
    linkName: 'link-${uniqueString(vnetId)}'
    tags: tags
  }
  dependsOn: [
    privateDnsZone
  ]
}]

// Create runner-hub links only for deployment-owned zones. A shared zone ID
// explicitly means the hub link already exists and must be reused, not duplicated.
module runnerHubVnetLink './private_dns_zone_vnet_link.bicep' = [for zone in managedDnsZones: if (!empty(runnerHubVnetId)) {
  name: 'dns-runner-link-${uniqueString(zone, runnerHubVnetId)}'
  params: {
    privateDnsZoneName: zone
    vnetId: runnerHubVnetId
    linkName: 'link-runner-${uniqueString(runnerHubVnetId)}'
    tags: tags
  }
  dependsOn: [
    privateDnsZone
  ]
}]

output blobDnsZoneId string = privateDnsZoneIds[0]
output fileDnsZoneId string = privateDnsZoneIds[1]
output queueDnsZoneId string = privateDnsZoneIds[2]
output tableDnsZoneId string = privateDnsZoneIds[3]
output dfsDnsZoneId string = privateDnsZoneIds[4]
output kvDnsZoneId string = privateDnsZoneIds[5]
output acrDnsZoneId string = privateDnsZoneIds[6]
output amlDnsZoneId string = privateDnsZoneIds[7]
output notebookDnsZoneId string = privateDnsZoneIds[8]
