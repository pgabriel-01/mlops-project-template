targetScope = 'subscription'

var roleName = guid(subscription().subscriptionId, 'azureml-namespace-bootstrap')

resource role 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: roleName
  properties: {
    assignableScopes: [
      subscription().id
    ]
    description: 'Invoke AKS Run Command and manage only the Azure ML namespace and service account.'
    permissions: [
      {
        actions: [
          'Microsoft.ContainerService/managedClusters/runCommand/action'
          'Microsoft.ContainerService/managedClusters/commandResults/read'
        ]
        dataActions: [
          'Microsoft.ContainerService/managedClusters/namespaces/read'
          'Microsoft.ContainerService/managedClusters/namespaces/write'
          'Microsoft.ContainerService/managedClusters/serviceaccounts/read'
          'Microsoft.ContainerService/managedClusters/serviceaccounts/write'
        ]
        notActions: []
        notDataActions: []
      }
    ]
    roleName: 'Azure ML Namespace Bootstrap'
    type: 'CustomRole'
  }
}

output roleId string = role.id
