using './main.bicep'

param location = 'eastus2'
param resourceGroupName = 'rg-mlops-arc-dev-eus2-001'
param hubVnetResourceGroupName = 'rg-mlops-hub-dev-eus2-001'
param hubVnetName = 'vnet-mlops-hub-dev-eus2-001'
param runnerSubnetName = 'snet-github-runners'
param runnerSubnetPrefix = '10.240.2.0/24'
param aksName = 'aks-mlops-arc-dev-eus2-001'
param nodeVmSize = 'Standard_D2ads_v6'
param systemNodeCount = 2
