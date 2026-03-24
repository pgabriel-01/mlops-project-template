targetScope = 'subscription'

param location string = 'eastus2'
param prefix string = 'mlops'
param postfix string = 'demo'
param env string = 'dev'
param adoServicePrincipalId string = ''
param amlComputeSku string = 'STANDARD_D16S_V3'

// Feature flags — control which optional modules are deployed
param enableMonitoring bool = true
param enableContainerRegistry bool = true
param enableComputeCluster bool = true
param enableVNet bool = false

// Tier 3 — Governance feature flags
param enableCMEK bool = false
param enableDefender bool = false
param projectNumber string = '001'

// Persona RBAC — Entra ID security group object IDs (empty = skip)
param teamLeadGroupId string = ''
param dataScientistGroupId string = ''
param mlEngineerGroupId string = ''

// Tier 4 — GenAI / Agent feature flags
param enableAIFoundry bool = false
param enableAPIManagement bool = false

// Key Vault settings
param kvEnablePurgeProtection bool = false
param kvSoftDeleteRetentionDays int = 7

// VNet settings (only used when enableVNet = true)
param vnetAddressPrefix string = '10.0.0.0/16'
param defaultSubnetPrefix string = '10.0.0.0/24'
param computeSubnetPrefix string = '10.0.1.0/24'
param peSubnetPrefix string = '10.0.2.0/24'

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
  ProjectNumber: projectNumber
}

var baseName  = '${prefix}-${postfix}${projectNumber}${env}'
var resourceGroupName = 'rg-${baseName}'

// ============================================================
// Phase 1 — Foundation: Resource Group, Managed Identity, VNet
// ============================================================

resource rg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
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
    vnetId: enableVNet ? vnet.outputs.vnetId : ''
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
      vnet.outputs.defaultSubnetId
      vnet.outputs.computeSubnetId
    ] : []
  }
}

// Key Vault
module kv './modules/key_vault.bicep' = {
  name: 'kv'
  scope: resourceGroup(rg.name)
  params: {
    baseName: '${prefix}${uniqueString(rg.id)}${env}'
    location: location
    tags: tags
    enablePurgeProtection: kvEnablePurgeProtection
    softDeleteRetentionDays: kvSoftDeleteRetentionDays
    enableNetworkIsolation: enableVNet
    allowedSubnetIds: enableVNet ? [
      vnet.outputs.defaultSubnetId
      vnet.outputs.computeSubnetId
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
    subnetId: enableVNet ? vnet.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones.outputs.blobDnsZoneId : ''
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
    subnetId: enableVNet ? vnet.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones.outputs.kvDnsZoneId : ''
  }
}

module peCr './modules/private_endpoint.bicep' = if (enableVNet && enableContainerRegistry) {
  name: 'pe-cr'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-cr-${baseName}'
    targetResourceId: enableContainerRegistry ? cr.outputs.crOut : ''
    groupId: 'registry'
    subnetId: enableVNet ? vnet.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones.outputs.acrDnsZoneId : ''
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
    appinsightid: enableMonitoring ? appi.outputs.appinsightOut : ''
    crid: enableContainerRegistry ? cr.outputs.crOut : ''
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
    subnetId: enableVNet ? vnet.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: enableVNet ? dnsZones.outputs.amlDnsZoneId : ''
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
    subnetId: enableVNet ? vnet.outputs.computeSubnetId : ''
  }
}

// ============================================================
// Phase 4 — Governance: Persona RBAC, CMEK, Defender
// ============================================================

// Persona RBAC: Team Lead (full access)
module rbacTeamLead './modules/rbac_persona_team_lead.bicep' = if (!empty(teamLeadGroupId)) {
  name: 'rbac-team-lead'
  scope: resourceGroup(rg.name)
  params: {
    principalId: teamLeadGroupId
    principalType: 'Group'
    workspaceId: mlw.outputs.amlsId
    storageAccountId: st.outputs.stoacctOut
    keyVaultId: kv.outputs.kvOut
    containerRegistryId: enableContainerRegistry ? cr.outputs.crOut : ''
  }
}

// Persona RBAC: Data Scientist (workspace + storage read)
module rbacDataScientist './modules/rbac_persona_data_scientist.bicep' = if (!empty(dataScientistGroupId)) {
  name: 'rbac-data-scientist'
  scope: resourceGroup(rg.name)
  params: {
    principalId: dataScientistGroupId
    principalType: 'Group'
    workspaceId: mlw.outputs.amlsId
    storageAccountId: st.outputs.stoacctOut
    keyVaultId: kv.outputs.kvOut
  }
}

// Persona RBAC: ML Engineer (workspace + storage + ACR push)
module rbacMlEngineer './modules/rbac_persona_ml_engineer.bicep' = if (!empty(mlEngineerGroupId)) {
  name: 'rbac-ml-engineer'
  scope: resourceGroup(rg.name)
  params: {
    principalId: mlEngineerGroupId
    principalType: 'Group'
    workspaceId: mlw.outputs.amlsId
    storageAccountId: st.outputs.stoacctOut
    keyVaultId: kv.outputs.kvOut
    containerRegistryId: enableContainerRegistry ? cr.outputs.crOut : ''
  }
}

// CMEK — Customer Managed Key encryption (requires purge-protected Key Vault)
module cmk './modules/cmk.bicep' = if (enableCMEK) {
  name: 'cmk'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    keyVaultId: kv.outputs.kvOut
    managedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
  }
}

// Defender for AI — subscription-level and resource-level protection
module defender './modules/defender.bicep' = if (enableDefender) {
  name: 'defender'
  scope: resourceGroup(rg.name)
  params: {
    workspaceId: mlw.outputs.amlsId
    storageAccountId: st.outputs.stoacctOut
    location: location
  }
}

// ============================================================
// Phase 5 — GenAI: AI Foundry Hub, Project, API Management
// ============================================================

// AI Foundry Hub — AI Services + Hub workspace for GenAI workloads
module aiFoundryHub './modules/ai_foundry_hub.bicep' = if (enableAIFoundry) {
  name: 'ai-foundry-hub'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    storageAccountId: st.outputs.stoacctOut
    keyVaultId: kv.outputs.kvOut
    managedIdentityId: mi.outputs.managedIdentityId
    enablePublicAccess: !enableVNet
  }
}

// AI Foundry Project — default project under the Hub
module aiFoundryProject './modules/ai_foundry_project.bicep' = if (enableAIFoundry) {
  name: 'ai-foundry-project'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    aiHubId: enableAIFoundry ? aiFoundryHub.outputs.aiHubId : ''
    managedIdentityId: mi.outputs.managedIdentityId
  }
}

// API Management — AI Gateway for rate limiting and load balancing model endpoints
module apim './modules/apim.bicep' = if (enableAPIManagement) {
  name: 'apim'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
  }
}
