targetScope = 'subscription'

param location string = 'westus2'
param prefix string
param postfix string
param env string
param adoServicePrincipalId string = ''

param tags object = {
  Owner: 'mlops-v2'
  Project: 'mlops-v2'
  Environment: env
  Toolkit: 'bicep'
  Name: prefix
}

var baseName  = '${prefix}-${postfix}${env}'
var resourceGroupName = 'rg-${baseName}'

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

// Storage Account
module st './modules/storage_account.bicep' = {
  name: 'st'
  scope: resourceGroup(rg.name)
  params: {
    baseName: '${uniqueString(rg.id)}${env}'
    location: location
    tags: tags
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
  }
}

// App Insights
module appi './modules/application_insights.bicep' = {
  name: 'appi'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    tags: tags
  }
}

// Container Registry
module cr './modules/container_registry.bicep' = {
  name: 'cr'
  scope: resourceGroup(rg.name)
  params: {
    baseName: '${uniqueString(rg.id)}${env}'
    location: location
    tags: tags
  }
}

// AML workspace with user-assigned identity and RBAC
module mlw './modules/aml_workspace.bicep' = {
  name: 'mlw'
  scope: resourceGroup(rg.name)
  params: {
    baseName: baseName
    location: location
    stoacctid: st.outputs.stoacctOut
    kvid: kv.outputs.kvOut
    appinsightid: appi.outputs.appinsightOut
    crid: cr.outputs.crOut
    managedIdentityId: mi.outputs.managedIdentityId
    managedIdentityPrincipalId: mi.outputs.managedIdentityPrincipalId
    adoServicePrincipalId: adoServicePrincipalId
    tags: tags
  }
}

// AML compute cluster
module mlwcc './modules/aml_computecluster.bicep' = {
  name: 'mlwcc'
  scope: resourceGroup(rg.name)
  params: {
    location: location
    workspaceName: mlw.outputs.amlsName
  }
}
