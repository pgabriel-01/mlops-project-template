param aksName string
param controlPlaneIdentityId string
param kubernetesVersion string
param location string
param logAnalyticsWorkspaceId string
param nodeVmSize string
param runnerSubnetId string
param systemNodeCount int
param tags object

resource aks 'Microsoft.ContainerService/managedClusters@2025-04-01' = {
  name: aksName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${controlPlaneIdentityId}': {}
    }
  }
  properties: {
    kubernetesVersion: empty(kubernetesVersion) ? null : kubernetesVersion
    dnsPrefix: aksName
    enableRBAC: true
    disableLocalAccounts: true
    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }
    apiServerAccessProfile: {
      enablePrivateCluster: true
      enablePrivateClusterPublicFQDN: false
      privateDNSZone: 'system'
    }
    aadProfile: {
      managed: true
      enableAzureRBAC: true
    }
    agentPoolProfiles: [
      {
        name: 'system'
        count: systemNodeCount
        vmSize: nodeVmSize
        mode: 'System'
        osType: 'Linux'
        osSKU: 'Ubuntu'
        type: 'VirtualMachineScaleSets'
        vnetSubnetID: runnerSubnetId
        enableAutoScaling: false
        enableNodePublicIP: false
        maxPods: 50
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
      outboundType: 'userAssignedNATGateway'
      podCidr: '10.244.0.0/16'
      serviceCidr: '10.245.0.0/16'
      dnsServiceIP: '10.245.0.10'
    }
    addonProfiles: {
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: logAnalyticsWorkspaceId
          useAADAuth: 'true'
        }
      }
    }
  }
  tags: tags
}

resource aksDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'aks-control-plane'
  scope: aks
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'kube-audit'
        enabled: true
      }
      {
        category: 'kube-audit-admin'
        enabled: true
      }
      {
        category: 'kube-apiserver'
        enabled: true
      }
      {
        category: 'guard'
        enabled: true
      }
    ]
  }
}

output aksName string = aks.name
