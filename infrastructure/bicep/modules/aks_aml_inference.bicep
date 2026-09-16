param clusterName string
param location string
param workspaceResourceId string
param workspaceManagedIdentityResourceId string
param workspaceManagedIdentityPrincipalId string
param namespaceBootstrapRoleId string
param inferenceIdentityClientId string
param inferenceNamespace string
param nodePoolName string
param nodeSubnetResourceId string
param nodeVmSize string
param nodeMinCount int
param nodeMaxCount int
param nodeMaxPods int
param extensionName string
param extensionReleaseTrain string
param extensionSslCname string
@secure()
param extensionTlsCertPem string
@secure()
param extensionTlsKeyPem string

var namespaceManifest = replace(
  replace(
    loadTextContent('../manifests/azureml-inference-namespace.yaml'),
    '__ONLINE_NAMESPACE__',
    inferenceNamespace
  ),
  '__ONLINE_INFERENCE_IDENTITY_CLIENT_ID__',
  inferenceIdentityClientId
)
var namespaceManifestBase64 = base64(namespaceManifest)

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

resource workspaceNamespaceBootstrapInvoker 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cluster.id, workspaceManagedIdentityPrincipalId, namespaceBootstrapRoleId)
  scope: cluster
  properties: {
    principalId: workspaceManagedIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: namespaceBootstrapRoleId
  }
}

resource namespaceBootstrap 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: take('aml-namespace-${uniqueString(cluster.id, inferenceNamespace)}', 64)
  location: location
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workspaceManagedIdentityResourceId}': {}
    }
  }
  properties: {
    azCliVersion: '2.90.0'
    cleanupPreference: 'Always'
    environmentVariables: [
      {
        name: 'NAMESPACE_MANIFEST_BASE64'
        value: namespaceManifestBase64
      }
    ]
    retentionInterval: 'P1D'
    scriptContent: '''
      set -euo pipefail
      for attempt in $(seq 1 12); do
        if az aks command invoke \
          --resource-group '${resourceGroup().name}' \
          --name '${clusterName}' \
          --command "echo $NAMESPACE_MANIFEST_BASE64 | base64 -d | kubectl apply -f -" \
          --only-show-errors \
          --output none; then
          exit 0
        fi
        echo "AKS Run Command attempt $attempt failed; waiting for RBAC propagation" >&2
        sleep 10
      done
      echo "Unable to apply the Azure ML namespace contract through AKS Run Command" >&2
      exit 1
    '''
  }
  dependsOn: [
    workspaceNamespaceBootstrapInvoker
  ]
}

resource amlExtension 'Microsoft.KubernetesConfiguration/extensions@2025-03-01' = {
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
    workspaceNamespaceBootstrapInvoker
    namespaceBootstrap
  ]
}

output extensionPrincipalId string = amlExtension.identity.principalId
output trustedAccessRoleBindingName string = trustedAccess.name
output nodePoolId string = inferencePool.id
output namespaceBootstrapName string = namespaceBootstrap.name
