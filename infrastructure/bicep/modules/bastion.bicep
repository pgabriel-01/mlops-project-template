param baseName string
param location string
param tags object
param bastionSubnetId string
param bastionSubnetPrefix string
param administrationSubnetId string
param adminUsername string = 'azureuser'
param vmSize string = 'Standard_D2s_v5'
param ubuntuImageVersion string
param azureCliVersion string
param azureMlExtensionVersion string
param azureAiMlVersion string
param azureIdentityVersion string
param shutdownTime string = '1900'
param shutdownTimeZone string = 'UTC'
param loginGroupObjectId string = ''

var jumpboxName = 'vm-dev-jumpbox-${baseName}'
var bootstrapSshPublicKey = trim(loadTextContent('../assets/dev-jumpbox-bootstrap.pub'))
var cloudInit = format('''
#cloud-config
package_update: true
packages:
  - ca-certificates
  - curl
  - gnupg
  - python3
  - python3-pip
  - python3-venv
bootcmd:
  - rm -f /home/{4}/.ssh/authorized_keys
runcmd:
  - install -d -m 0755 /etc/apt/keyrings
  - curl --fail --silent --show-error https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /etc/apt/keyrings/microsoft.gpg
  - chmod 0644 /etc/apt/keyrings/microsoft.gpg
  - printf '%s\n' 'Types: deb' 'URIs: https://packages.microsoft.com/repos/azure-cli/' 'Suites: noble' 'Components: main' 'Architectures: amd64' 'Signed-by: /etc/apt/keyrings/microsoft.gpg' > /etc/apt/sources.list.d/azure-cli.sources
  - apt-get update
  - apt-get install -y --no-install-recommends azure-cli={0}
  - install -d -m 0755 /opt/az-extensions
  - printf '%s\n' 'export AZURE_EXTENSION_DIR=/opt/az-extensions' > /etc/profile.d/azure-cli-extensions.sh
  - chmod 0644 /etc/profile.d/azure-cli-extensions.sh
  - AZURE_EXTENSION_DIR=/opt/az-extensions az extension add --name ml --version {1} --yes
  - test "$(AZURE_EXTENSION_DIR=/opt/az-extensions az extension show --name ml --query version --output tsv)" = "{1}"
  - python3 -m venv /opt/azureml-admin
  - /opt/azureml-admin/bin/pip install --disable-pip-version-check --no-cache-dir azure-ai-ml=={2} azure-identity=={3}
  - chown -R root:root /opt/azureml-admin
  - chmod -R go-w /opt/azureml-admin
''', azureCliVersion, azureMlExtensionVersion, azureAiMlVersion, azureIdentityVersion, adminUsername)

resource jumpboxNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-dev-jumpbox-${baseName}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowSshFromAzureBastionSubnet'
        properties: {
          priority: 100
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourceAddressPrefix: bastionSubnetPrefix
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'DenyOtherInbound'
        properties: {
          priority: 4096
          access: 'Deny'
          direction: 'Inbound'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource jumpboxNic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-dev-jumpbox-${baseName}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'primary'
        properties: {
          primary: true
          subnet: {
            id: administrationSubnetId
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
    networkSecurityGroup: {
      id: jumpboxNsg.id
    }
  }
}

resource jumpboxVm 'Microsoft.Compute/virtualMachines@2025-04-01' = {
  name: jumpboxName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  tags: union(tags, {
    DisplayName: 'Dev jumpbox'
    Purpose: 'Private human administration only'
  })
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: 'dev-jumpbox'
      adminUsername: adminUsername
      customData: base64(cloudInit)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: bootstrapSshPublicKey
            }
          ]
        }
      }
    }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: {
        secureBootEnabled: true
        vTpmEnabled: true
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: ubuntuImageVersion
      }
      osDisk: {
        createOption: 'FromImage'
        caching: 'ReadWrite'
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: jumpboxNic.id
          properties: {
            primary: true
          }
        }
      ]
    }
  }
}

resource aadSsh 'Microsoft.Compute/virtualMachines/extensions@2025-04-01' = {
  parent: jumpboxVm
  name: 'AADSSHLoginForLinux'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.ActiveDirectory'
    type: 'AADSSHLoginForLinux'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    settings: {}
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2025-07-01' = {
  name: 'bastion-private-${baseName}'
  location: location
  tags: tags
  sku: {
    name: 'Premium'
  }
  properties: {
    enablePrivateOnlyBastion: true
    enableTunneling: true
    ipConfigurations: [
      {
        name: 'private'
        properties: {
          subnet: {
            id: bastionSubnetId
          }
        }
      }
    ]
    scaleUnits: 2
  }
}

resource shutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = {
  name: 'shutdown-computevm-${jumpboxVm.name}'
  location: location
  tags: tags
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    targetResourceId: jumpboxVm.id
    timeZoneId: shutdownTimeZone
    dailyRecurrence: {
      time: shutdownTime
    }
    notificationSettings: {
      status: 'Disabled'
      timeInMinutes: 30
      emailRecipient: ''
      webhookUrl: ''
    }
  }
}

resource jumpboxUserLogin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(loginGroupObjectId)) {
  name: guid(jumpboxVm.id, loginGroupObjectId, 'fb879df8-f326-4884-b1cf-06f3ad86be52') // Virtual Machine User Login
  scope: jumpboxVm
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'fb879df8-f326-4884-b1cf-06f3ad86be52'
    )
    principalId: loginGroupObjectId
    principalType: 'Group'
  }
}

resource jumpboxVmReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(loginGroupObjectId)) {
  name: guid(jumpboxVm.id, loginGroupObjectId, 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  scope: jumpboxVm
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'acdd72a7-3385-48ef-bd42-f606fba81ae7'
    )
    principalId: loginGroupObjectId
    principalType: 'Group'
  }
}

resource jumpboxNicReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(loginGroupObjectId)) {
  name: guid(jumpboxNic.id, loginGroupObjectId, 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  scope: jumpboxNic
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'acdd72a7-3385-48ef-bd42-f606fba81ae7'
    )
    principalId: loginGroupObjectId
    principalType: 'Group'
  }
}

resource bastionReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(loginGroupObjectId)) {
  name: guid(bastion.id, loginGroupObjectId, 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  scope: bastion
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'acdd72a7-3385-48ef-bd42-f606fba81ae7'
    )
    principalId: loginGroupObjectId
    principalType: 'Group'
  }
}

output bastionName string = bastion.name
output bastionId string = bastion.id
output jumpboxVmName string = jumpboxVm.name
output jumpboxVmId string = jumpboxVm.id
output jumpboxPrincipalId string = jumpboxVm.identity.principalId
output jumpboxPrivateIp string = jumpboxNic.properties.ipConfigurations[0].properties.privateIPAddress
