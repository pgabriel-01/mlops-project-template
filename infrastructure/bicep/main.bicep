targetScope = 'subscription'

param location string = 'eastus2'
param prefix string = 'mlops'
param postfix string = 'demo'
param env string = 'dev'
param ciPrincipalObjectId string = ''
param amlComputeSku string = 'STANDARD_D16S_V3'
param imageBuildComputeName string = 'cpu-cluster'

// Feature flags — control which optional modules are deployed
param enableMonitoring bool = true
param enableContainerRegistry bool = true
param enableComputeCluster bool = true
param enableVNet bool = false
param runnerHubVnetResourceId string = ''
param manageRunnerHubToWorkloadPeering bool = false
param sharedPrivateDnsZoneResourceIds object = {}

// Private Azure ML Kubernetes online inference on an existing AKS cluster
param enablePrivateAksInference bool = false
param completePrivateAksInferenceDeployment bool = true
param aksClusterResourceId string = ''
param aksNodeSubnetResourceId string = ''
param onlineComputeName string = 'aks-inference'
param onlineMlflowNoCode bool = true
param onlineEnvironmentName string = ''
param onlineEnvironmentVersion string = ''
param onlineEnvironmentImage string = ''
param onlineNamespace string = 'azureml-inference'
param onlineServiceAccountName string = 'default'
param onlineNodePoolName string = 'mlinference'
param onlineNodeVmSize string = 'Standard_D4s_v3'
param onlineNodeMinCount int = 3
param onlineNodeMaxCount int = 6
param onlineNodeMaxPods int = 30
param onlineInstanceTypeName string = 'cpu-small'
param onlineCpuRequest string = '500m'
param onlineCpuLimit string = '2'
param onlineMemoryRequest string = '1Gi'
param onlineMemoryLimit string = '4Gi'
param amlKubernetesExtensionName string = 'azureml'
param amlKubernetesExtensionReleaseTrain string = 'stable'
param amlKubernetesExtensionSslCname string = ''
@secure()
param amlKubernetesExtensionTlsCertPem string = ''
@secure()
param amlKubernetesExtensionTlsKeyPem string = ''

// Tier 3 — Governance feature flags
param enableCMEK bool = false
param enableDefender bool = false
param projectNumber string = '001'

// Persona RBAC — Entra ID security group object IDs (empty = skip)
param teamLeadGroupId string = ''
param dataScientistGroupId string = ''
param mlEngineerGroupId string = ''

// AML Registry — cross-workspace model promotion
param enableAMLRegistry bool = false

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

// Bastion settings (only used when enableBastion = true; requires enableVNet)
param enableBastion bool = false
param bastionSubnetPrefix string = '10.0.3.0/26'

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

var hasOnlineEnvironmentName = !empty(onlineEnvironmentName)
var hasOnlineEnvironmentVersion = !empty(onlineEnvironmentVersion)
var hasOnlineEnvironmentImage = !empty(onlineEnvironmentImage)
var hasAnyOnlineEnvironmentInput = hasOnlineEnvironmentName || hasOnlineEnvironmentVersion || hasOnlineEnvironmentImage
var hasCompleteOnlineEnvironment = hasOnlineEnvironmentName && hasOnlineEnvironmentVersion && hasOnlineEnvironmentImage

var mlflowNoCodeEnvironmentValidated = onlineMlflowNoCode && hasAnyOnlineEnvironmentInput
  ? fail('MLflow no-code mode cannot define an online environment name, version, or image.')
  : true
var imageOnlyEnvironmentValidated = !onlineMlflowNoCode && ((enablePrivateAksInference && !hasCompleteOnlineEnvironment) || (hasAnyOnlineEnvironmentInput && !hasCompleteOnlineEnvironment))
  ? fail('Image-only mode requires an online environment name, version, and immutable image together.')
  : true
var privateAksBootstrapPrincipalValidated = enablePrivateAksInference && empty(ciPrincipalObjectId)
  ? fail('Private AKS inference requires the GitHub OIDC principal object ID.')
  : true

var baseName  = '${prefix}-${postfix}${projectNumber}${env}'
var resourceGroupName = 'rg-${baseName}'
var hasRunnerHub = !empty(runnerHubVnetResourceId)
var runnerHubResourceIdParts = split(runnerHubVnetResourceId, '/')
var runnerHubSubscriptionId = hasRunnerHub ? runnerHubResourceIdParts[2] : subscription().subscriptionId
var runnerHubResourceGroupName = hasRunnerHub ? runnerHubResourceIdParts[4] : resourceGroupName
var runnerHubVnetName = hasRunnerHub ? runnerHubResourceIdParts[8] : ''
var spokeToRunnerHubPeeringName = 'peer-runner-${uniqueString(rg.id, runnerHubVnetResourceId)}'
var runnerHubToSpokePeeringName = 'peer-workload-${uniqueString(rg.id, runnerHubVnetResourceId)}'
var keyVaultPrefix = take(replace(toLower(prefix), '-', ''), 5)
var keyVaultEnvironment = take(replace(toLower(env), '-', ''), 3)
var keyVaultName = 'kv-${keyVaultPrefix}${uniqueString(rg.id)}${keyVaultEnvironment}'
var aksResourceIdParts = split(aksClusterResourceId, '/')
var aksSubscriptionId = enablePrivateAksInference ? aksResourceIdParts[2] : subscription().subscriptionId
var aksResourceGroupName = enablePrivateAksInference ? aksResourceIdParts[4] : resourceGroupName
var aksClusterName = enablePrivateAksInference ? aksResourceIdParts[8] : ''

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
    enableBastion: enableBastion
    bastionSubnetPrefix: bastionSubnetPrefix
  }
}

// Private DNS Zones — conditional on enableVNet
module dnsZones './modules/private_dns_zones.bicep' = if (enableVNet) {
  name: 'dnsZones'
  scope: resourceGroup(rg.name)
  params: {
    tags: tags
    vnetId: enableVNet ? vnet!.outputs.vnetId : ''
    runnerHubVnetId: (enableVNet && hasRunnerHub) ? runnerHubVnetResourceId : ''
    sharedPrivateDnsZoneResourceIds: sharedPrivateDnsZoneResourceIds
  }
}

module spokeToRunnerHub './modules/vnet_peering.bicep' = if (enableVNet && hasRunnerHub) {
  name: 'peer-workload-to-runner-hub'
  scope: resourceGroup(rg.name)
  params: {
    localVnetName: vnet!.outputs.vnetName
    remoteVnetId: runnerHubVnetResourceId
    peeringName: spokeToRunnerHubPeeringName
  }
}

module runnerHubToSpoke './modules/vnet_peering.bicep' = if (enableVNet && hasRunnerHub && manageRunnerHubToWorkloadPeering) {
  name: 'peer-runner-hub-to-${uniqueString(rg.id)}'
  scope: resourceGroup(runnerHubSubscriptionId, runnerHubResourceGroupName)
  params: {
    localVnetName: runnerHubVnetName
    remoteVnetId: vnet!.outputs.vnetId
    peeringName: runnerHubToSpokePeeringName
  }
}

// Bastion + Jump Box — conditional on enableBastion (requires enableVNet)
module bastion './modules/bastion.bicep' = if (enableVNet && enableBastion) {
  name: 'bastion'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    bastionSubnetId: vnet!.outputs.bastionSubnetId
    defaultSubnetId: vnet!.outputs.defaultSubnetId
    keyVaultName: kv.outputs.kvName
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
    keyVaultName: keyVaultName
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
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.blobDnsZoneId] : []
  }
}

module peStorageFile './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage-file'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-st-file-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'file'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.fileDnsZoneId] : []
  }
}

module peStorageQueue './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage-queue'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-st-queue-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'queue'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.queueDnsZoneId] : []
  }
}

module peStorageTable './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage-table'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-st-table-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'table'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.tableDnsZoneId] : []
  }
}

module peStorageDfs './modules/private_endpoint.bicep' = if (enableVNet) {
  name: 'pe-storage-dfs'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-st-dfs-${baseName}'
    targetResourceId: st.outputs.stoacctOut
    groupId: 'dfs'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.dfsDnsZoneId] : []
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
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.kvDnsZoneId] : []
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
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.acrDnsZoneId] : []
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
    ciPrincipalObjectId: ciPrincipalObjectId
    enableNetworkIsolation: enableVNet
    imageBuildComputeName: imageBuildComputeName
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
    privateDnsZoneIds: enableVNet ? [
      dnsZones!.outputs.amlDnsZoneId
      dnsZones!.outputs.notebookDnsZoneId
    ] : []
  }
}

// AML compute cluster — conditional on enableComputeCluster
module mlwcc './modules/aml_computecluster.bicep' = if (enableComputeCluster) {
  name: 'mlwcc'
  scope: resourceGroup(rg.name)
  dependsOn: [
    peMlw
  ]
  params: {
    location: location
    workspaceName: mlw.outputs.amlsName
    computeClusterName: imageBuildComputeName
    vmSku: amlComputeSku
    managedIdentityId: mi.outputs.managedIdentityId
    subnetId: enableVNet ? vnet!.outputs.computeSubnetId : ''
  }
}

resource existingAks 'Microsoft.ContainerService/managedClusters@2025-04-01' existing = if (enablePrivateAksInference) {
  name: aksClusterName
  scope: resourceGroup(aksSubscriptionId, aksResourceGroupName)
}

module amlKubernetesIdentity './modules/aml_kubernetes_identity.bicep' = if (enablePrivateAksInference) {
  name: 'aml-kubernetes-identity'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    oidcIssuerUrl: existingAks!.properties.oidcIssuerProfile.issuerURL
    namespace: onlineNamespace
    serviceAccountName: onlineServiceAccountName
    storageAccountId: st.outputs.stoacctOut
    containerRegistryId: cr!.outputs.crOut
    workspaceManagedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
  }
}

module aksNamespaceBootstrapRole './modules/aks_run_command_role.bicep' = if (enablePrivateAksInference) {
  name: 'aks-run-command-role'
  scope: subscription(aksSubscriptionId)
}

module aksAmlInference './modules/aks_aml_inference.bicep' = if (enablePrivateAksInference) {
  name: 'aks-aml-inference'
  scope: resourceGroup(aksSubscriptionId, aksResourceGroupName)
  params: {
    clusterName: aksClusterName
    workspaceResourceId: mlw.outputs.amlsId
    workspaceManagedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
    namespaceBootstrapRoleId: aksNamespaceBootstrapRole!.outputs.roleId
    namespaceBootstrapPrincipalId: ciPrincipalObjectId
    nodePoolName: onlineNodePoolName
    nodeSubnetResourceId: aksNodeSubnetResourceId
    nodeVmSize: onlineNodeVmSize
    nodeMinCount: onlineNodeMinCount
    nodeMaxCount: onlineNodeMaxCount
    nodeMaxPods: onlineNodeMaxPods
    extensionName: amlKubernetesExtensionName
    extensionReleaseTrain: amlKubernetesExtensionReleaseTrain
    deployExtension: completePrivateAksInferenceDeployment
    extensionTlsCertPem: amlKubernetesExtensionTlsCertPem
    extensionTlsKeyPem: amlKubernetesExtensionTlsKeyPem
    extensionSslCname: amlKubernetesExtensionSslCname
  }
}

module amlOnlineEnvironment './modules/aml_environment.bicep' = if (enablePrivateAksInference && !onlineMlflowNoCode) {
  name: 'aml-online-environment'
  scope: resourceGroup(rg.name)
  params: {
    workspaceName: mlw.outputs.amlsName
    environmentName: onlineEnvironmentName
    environmentVersion: onlineEnvironmentVersion
    imageUri: onlineEnvironmentImage
  }
  dependsOn: [
    peMlw
  ]
}

module amlKubernetesCompute './modules/aml_kubernetes_compute.bicep' = if (enablePrivateAksInference && completePrivateAksInferenceDeployment) {
  name: 'aml-kubernetes-compute'
  scope: resourceGroup(rg.name)
  params: {
    workspaceName: mlw.outputs.amlsName
    location: location
    computeName: onlineComputeName
    clusterResourceId: aksClusterResourceId
    namespace: onlineNamespace
    identityId: amlKubernetesIdentity!.outputs.identityId
    extensionPrincipalId: aksAmlInference!.outputs.extensionPrincipalId
    extensionReleaseTrain: amlKubernetesExtensionReleaseTrain
    instanceTypeName: onlineInstanceTypeName
    cpuRequest: onlineCpuRequest
    cpuLimit: onlineCpuLimit
    memoryRequest: onlineMemoryRequest
    memoryLimit: onlineMemoryLimit
  }
  dependsOn: [
    peMlw
  ]
}

// AML Registry — cross-workspace model/asset promotion
module amlReg './modules/aml_registry.bicep' = if (enableAMLRegistry) {
  name: 'aml-registry'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
    enablePublicAccess: !enableVNet
    managedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
    ciPrincipalObjectId: ciPrincipalObjectId
  }
}

// AML Registry private endpoint
module peAmlReg './modules/private_endpoint.bicep' = if (enableVNet && enableAMLRegistry) {
  name: 'pe-aml-registry'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-reg-${baseName}'
    targetResourceId: enableAMLRegistry ? amlReg!.outputs.registryId : ''
    groupId: 'amlregistry'
    subnetId: enableVNet ? vnet!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneIds: enableVNet ? [dnsZones!.outputs.amlDnsZoneId] : []
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
    containerRegistryId: enableContainerRegistry ? cr!.outputs.crOut : ''
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
    containerRegistryId: enableContainerRegistry ? cr!.outputs.crOut : ''
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
    aiHubId: enableAIFoundry ? aiFoundryHub!.outputs.aiHubId : ''
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

output resourceGroupName string = rg.name
output workspaceName string = mlw.outputs.amlsName
output storageAccountName string = st.outputs.stoacctName
output keyVaultName string = kv.outputs.kvName
output containerRegistryName string = enableContainerRegistry ? cr!.outputs.crName : ''
output runnerHubIntegrationEnabled bool = enableVNet && hasRunnerHub
output runnerHubReciprocalPeeringManaged bool = enableVNet && hasRunnerHub && manageRunnerHubToWorkloadPeering
output runnerHubReciprocalPeeringCommand string = (enableVNet && hasRunnerHub && !manageRunnerHubToWorkloadPeering) ? 'az network vnet peering create --subscription "${runnerHubSubscriptionId}" --resource-group "${runnerHubResourceGroupName}" --vnet-name "${runnerHubVnetName}" --name "${runnerHubToSpokePeeringName}" --remote-vnet "${vnet!.outputs.vnetId}" --allow-vnet-access --allow-forwarded-traffic' : ''
output privateAksInferenceEnabled bool = enablePrivateAksInference
output onlineComputeName string = enablePrivateAksInference && completePrivateAksInferenceDeployment ? amlKubernetesCompute!.outputs.computeName : ''
output onlineEnvironmentId string = enablePrivateAksInference && !onlineMlflowNoCode ? amlOnlineEnvironment!.outputs.environmentId : ''
output onlineConfigurationValidated bool = mlflowNoCodeEnvironmentValidated && imageOnlyEnvironmentValidated && privateAksBootstrapPrincipalValidated
output onlineNamespace string = enablePrivateAksInference ? onlineNamespace : ''
output aksClusterId string = enablePrivateAksInference ? aksClusterResourceId : ''
output legacyNamespaceBootstrapRoleAssignmentId string = enablePrivateAksInference ? aksAmlInference!.outputs.legacyNamespaceBootstrapRoleAssignmentId : ''
output onlineInferenceIdentityId string = enablePrivateAksInference ? amlKubernetesIdentity!.outputs.identityId : ''
output onlineInferenceIdentityClientId string = enablePrivateAksInference ? amlKubernetesIdentity!.outputs.identityClientId : ''
output onlineInferenceServiceAccountName string = enablePrivateAksInference ? onlineServiceAccountName : ''
