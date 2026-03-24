targetScope = 'subscription'

param location string = 'westus2'
param prefix string
param postfix string
param env string 

// Feature flags — control which optional modules are deployed
param enableMonitoring bool = true
param enableContainerRegistry bool = true
param enableComputeCluster bool = true
param enableVNet bool = false

// Key Vault settings
param kvEnablePurgeProtection bool = false
param kvSoftDeleteRetentionDays int = 7

// VNet settings (only used when enableVNet = true)
param vnetAddressPrefix string = '10.0.0.0/16'
param defaultSubnetPrefix string = '10.0.0.0/24'
param computeSubnetPrefix string = '10.0.1.0/24'
param peSubnetPrefix string = '10.0.2.0/24'

// Compute cluster VM SKU
param amlComputeSku string = 'Standard_DS3_v2'

// Object ID of the ADO service connection's service principal. When set, the
// pipeline SP is granted the data-plane roles it needs to run AML jobs.
param adoServicePrincipalId string = ''

// Tag parameters
param tagCostCenter string = ''
param tagManagedBy string = 'bicep'

param tags object = {
  Owner: 'mlops-v2'
  Project: prefix
  Environment: env
  Toolkit: 'bicep'
  Name: prefix
  CostCenter: tagCostCenter
  ManagedBy: tagManagedBy
}

var baseName  = '${prefix}-${postfix}${env}'
var resourceGroupName = 'rg-${baseName}'

// ============================================================
// Phase 1 — Foundation: Resource Group, Managed Identity, VNet
// ============================================================

resource rg 'Microsoft.Resources/resourceGroups@2020-06-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// Managed Identity for AML workspace
module mi './modules/managed_identity.bicep' = {
  name: 'mi'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    managedIdentityName: 'id-${baseName}'
    tags: tags
  }
}

// VNet — conditional on enableVNet
module vnet './modules/vnet.bicep' = if (enableVNet) {
  name: 'vnet'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    vnetAddressPrefix: vnetAddressPrefix
    defaultSubnetPrefix: defaultSubnetPrefix
    computeSubnetPrefix: computeSubnetPrefix
    privateEndpointSubnetPrefix: peSubnetPrefix
  }
}

// Private DNS Zones — conditional on enableVNet
module dnsZones './modules/private_dns_zones.bicep' = if (enableVNet) {
  name: 'dnsZones'
  scope: resourceGroup(rg.name)
  params: {
    tags: tags
    vnetId: enableVNet ? vnet!.outputs.vnetId : ''
  }
}

// ============================================================
// Phase 2 — Core Infrastructure: Storage, KV, ACR, App Insights
// ============================================================

// Storage Account
module st './modules/storage_account.bicep' = {
  name: 'st'
  scope: resourceGroup(rg.name)
  params: {
    baseName: '${uniqueString(rg.id)}${env}'
    location: location
    tags: tags
    enableNetworkIsolation: enableVNet
    allowedSubnetIds: enableVNet ? [
      vnet!.outputs.defaultSubnetId
      vnet!.outputs.computeSubnetId
    ] : []
  }
}

// Key Vault
module kv './modules/key_vault.bicep' = {
  name: 'kv'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    enablePurgeProtection: kvEnablePurgeProtection
    softDeleteRetentionDays: kvSoftDeleteRetentionDays
    enableNetworkIsolation: enableVNet
    allowedSubnetIds: enableVNet ? [
      vnet!.outputs.defaultSubnetId
      vnet!.outputs.computeSubnetId
    ] : []
  }
}

// App Insights — conditional on enableMonitoring
module appi './modules/application_insights.bicep' = if (enableMonitoring) {
  name: 'appi'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
  }
}

// Container Registry — conditional on enableContainerRegistry
module cr './modules/container_registry.bicep' = if (enableContainerRegistry) {
  name: 'cr'
  scope: resourceGroup(rg.name)
  params: {
    baseName: '${uniqueString(rg.id)}${env}'
    location: location
    tags: tags
    enableNetworkIsolation: enableVNet
  }
}

// Private Endpoints — conditional on enableVNet
module peStorage './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-st-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'blob'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones!.outputs.blobDnsZoneId : ''
  }
}

// Storage file private endpoint — AML uses the file share (workspacefilestore)
// in addition to blob, so it also needs a PE or the file datastore is
// unreachable once public network access is denied.
module peStorageFile './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage-file'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-stfile-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'file'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones!.outputs.fileDnsZoneId : ''
  }
}

module peKeyVault './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-kv'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-kv-${baseName}'
    targetResourceId: kv.outputs.kvOut
    groupId: 'vault'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones!.outputs.kvDnsZoneId : ''
  }
}

module peCr './modules/private_endpoint.bicep' = if (enableVNet && enableContainerRegistry) {
  name: 'pe-cr'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-cr-${baseName}'
    targetResourceId: enableContainerRegistry ? cr!.outputs.crOut : ''
    groupId: 'registry'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones!.outputs.acrDnsZoneId : ''
  }
}

// ============================================================
// Phase 3 — AI Platform: AML Workspace, Compute, RBAC
// ============================================================

// AML workspace with user-assigned identity and RBAC
module mlw './modules/aml_workspace.bicep' = {
  name: 'mlw'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    stoacctid: st.outputs.stoacctOut
    kvid: kv.outputs.kvOut
    appinsightid: enableMonitoring ? appi!.outputs.appinsightOut : ''
    crid: enableContainerRegistry ? cr!.outputs.crOut : ''
    managedIdentityId: mi.outputs.managedIdentityId
    managedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
    adoServicePrincipalId: adoServicePrincipalId
    enableNetworkIsolation: enableVNet
    tags: tags
  }
}

// AML workspace private endpoint
module peMlw './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-mlw'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-mlw-${baseName}'
    targetResourceId: mlw.outputs.amlsId
    groupId: 'amlworkspace'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones!.outputs.amlDnsZoneId : ''
  }
}

// AML compute cluster — conditional on enableComputeCluster
module mlwcc './modules/aml_computecluster.bicep' = if (enableComputeCluster) {
  name: 'mlwcc'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    workspaceName: mlw.outputs.amlsName
    vmSku: amlComputeSku
    managedIdentityId: mi.outputs.managedIdentityId
    subnetId: enableVNet ? vnet!.outputs.computeSubnetId : ''
  }
}
