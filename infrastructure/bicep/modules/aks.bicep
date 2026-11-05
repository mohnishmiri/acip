param name string
param location string
param tags object
param kubernetesVersion string = ''
param systemVmSize string
param userVmSize string
param userMinCount int
param userMaxCount int
param logAnalyticsWorkspaceId string
param acrId string
@description('Existing subnet for nodes (empty = AKS-managed VNet)')
param subnetId string = ''

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource aks 'Microsoft.ContainerService/managedClusters@2024-02-01' = {
  name: name
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    kubernetesVersion: empty(kubernetesVersion) ? null : kubernetesVersion
    dnsPrefix: name
    enableRBAC: true
    aadProfile: {
      managed: true
      enableAzureRBAC: true
    }
    disableLocalAccounts: true
    oidcIssuerProfile: { enabled: true }
    securityProfile: {
      workloadIdentity: { enabled: true }
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
    }
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        vmSize: systemVmSize
        count: 2
        osType: 'Linux'
        osSKU: 'AzureLinux'
        availabilityZones: ['1', '2', '3']
        vnetSubnetID: empty(subnetId) ? null : subnetId
        nodeTaints: ['CriticalAddonsOnly=true:NoSchedule']
      }
      {
        name: 'user'
        mode: 'User'
        vmSize: userVmSize
        osType: 'Linux'
        osSKU: 'AzureLinux'
        enableAutoScaling: true
        minCount: userMinCount
        maxCount: userMaxCount
        count: userMinCount
        availabilityZones: ['1', '2', '3']
        vnetSubnetID: empty(subnetId) ? null : subnetId
      }
    ]
    addonProfiles: {
      azureKeyvaultSecretsProvider: {
        enabled: true
        config: { enableSecretRotation: 'true', rotationPollInterval: '2m' }
      }
      omsagent: {
        enabled: true
        config: { logAnalyticsWorkspaceResourceID: logAnalyticsWorkspaceId }
      }
    }
    ingressProfile: {
      webAppRouting: { enabled: true }
    }
    autoUpgradeProfile: { upgradeChannel: 'patch' }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: last(split(acrId, '/'))
}

// Kubelet identity pulls images from ACR (no registry credentials in the cluster)
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrId, aks.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

output name string = aks.name
output oidcIssuerUrl string = aks.properties.oidcIssuerProfile.issuerURL
