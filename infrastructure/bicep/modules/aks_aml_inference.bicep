param clusterName string
param workspaceResourceId string
param workspaceManagedIdentityPrincipalId string
param namespaceBootstrapRoleId string
param namespaceBootstrapPrincipalId string
param nodePoolName string
param nodeSubnetResourceId string
param nodeVmSize string
param nodeMinCount int
param nodeMaxCount int
param nodeMaxPods int
param extensionName string
param extensionReleaseTrain string
param extensionSslCname string
param deployExtension bool
@secure()
param extensionTlsCertPem string
@secure()
param extensionTlsKeyPem string

var readerRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'acdd72a7-3385-48ef-bd42-f606fba81ae7'
)
var kubernetesExtensionContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '85cb6faf-e071-4c9b-8136-154b5a04f717'
)

resource cluster 'Microsoft.ContainerService/managedClusters@2025-04-01' existing = {
  name: clusterName
}

resource inferencePool 'Microsoft.ContainerService/managedClusters/agentPools@2025-04-01' = {
  name: nodePoolName
  parent: cluster
  properties: {
    count: nodeMinCount
    enableAutoScaling: true
    enableEncryptionAtHost: true
    enableNodePublicIP: false
    maxCount: nodeMaxCount
    maxPods: nodeMaxPods
    minCount: nodeMinCount
    mode: 'User'
    nodeLabels: {
      'ml.azure.com/inference': 'true'
      workload: 'azureml-inference'
    }
    nodeTaints: [
      'ml.azure.com/amlarc=true:NoSchedule'
    ]
    osDiskType: 'Managed'
    osSKU: 'Ubuntu'
    osType: 'Linux'
    scaleDownMode: 'Delete'
    type: 'VirtualMachineScaleSets'
    vnetSubnetID: nodeSubnetResourceId
    vmSize: nodeVmSize
  }
}

resource trustedAccess 'Microsoft.ContainerService/managedClusters/trustedAccessRoleBindings@2025-07-01' = {
  name: take('aml-${uniqueString(workspaceResourceId)}', 24)
  parent: cluster
  properties: {
    roles: [
      'Microsoft.MachineLearningServices/workspaces/mlworkload'
    ]
    sourceResourceId: workspaceResourceId
  }
}

resource workspaceClusterReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cluster.id, workspaceManagedIdentityPrincipalId, readerRoleId)
  scope: cluster
  properties: {
    principalId: workspaceManagedIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: readerRoleId
  }
}

resource workspaceExtensionContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(
    cluster.id,
    workspaceManagedIdentityPrincipalId,
    kubernetesExtensionContributorRoleId
  )
  scope: cluster
  properties: {
    principalId: workspaceManagedIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: kubernetesExtensionContributorRoleId
  }
}

resource namespaceBootstrapInvoker 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cluster.id, namespaceBootstrapPrincipalId, namespaceBootstrapRoleId)
  scope: cluster
  properties: {
    principalId: namespaceBootstrapPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: namespaceBootstrapRoleId
  }
}

resource amlExtension 'Microsoft.KubernetesConfiguration/extensions@2025-03-01' = if (deployExtension) {
  name: extensionName
  scope: cluster
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    autoUpgradeMode: 'compatible'
    autoUpgradeMinorVersion: true
    configurationSettings: {
      allowInsecureConnections: 'False'
      enableInference: 'True'
      enableTraining: 'False'
      inferenceRouterHA: 'True'
      inferenceRouterServiceType: 'LoadBalancer'
      internalLoadBalancerProvider: 'azure'
      nodeSelector: 'ml.azure.com/inference=true'
      sslCname: extensionSslCname
    }
    configurationProtectedSettings: {
      sslCertPemFile: extensionTlsCertPem
      sslKeyPemFile: extensionTlsKeyPem
    }
    extensionType: 'Microsoft.AzureML.Kubernetes'
    releaseTrain: extensionReleaseTrain
    scope: {
      cluster: {
        releaseNamespace: 'azureml'
      }
    }
  }
  dependsOn: [
    inferencePool
    trustedAccess
    workspaceClusterReader
    workspaceExtensionContributor
    namespaceBootstrapInvoker
  ]
}

output extensionPrincipalId string = deployExtension ? amlExtension!.identity.principalId : ''
output trustedAccessRoleBindingName string = trustedAccess.name
output nodePoolId string = inferencePool.id
output legacyNamespaceBootstrapRoleAssignmentId string = extensionResourceId(
  cluster.id,
  'Microsoft.Authorization/roleAssignments',
  guid(cluster.id, workspaceManagedIdentityPrincipalId, namespaceBootstrapRoleId)
)
