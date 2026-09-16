targetScope = 'subscription'

var roleName = guid(subscription().subscriptionId, 'azureml-namespace-bootstrap')

resource role 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: roleName
  properties: {
    assignableScopes: [
      subscription().id
    ]
    description: 'Invoke AKS Run Command only to apply the Azure ML namespace contract.'
    permissions: [
      {
        actions: [
          'Microsoft.ContainerService/managedClusters/runCommand/action'
          'Microsoft.ContainerService/managedClusters/commandResults/read'
        ]
        notActions: []
      }
    ]
    roleName: 'Azure ML Namespace Bootstrap'
    type: 'CustomRole'
  }
}

output roleId string = role.id
