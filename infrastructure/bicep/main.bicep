// Azure Cost Intelligence Platform -- platform resources (resource-group scope).
// Deploy:  az deployment group create -g <rg> -f main.bicep -p main.parameters.json
//
// Creates: Log Analytics, ACR, AKS (OIDC issuer, Workload Identity, Key Vault CSI add-on,
// Container Insights, application routing), PostgreSQL Flexible Server, Storage account +
// export container, Key Vault (RBAC) and the role assignments the EXISTING collection
// service principal needs on those resources. Subscription-level roles (Cost Management
// Reader) are assigned by infrastructure/scripts/assign-roles.sh because they target other
// subscriptions. The federated credential on the existing app registration is created by
// infrastructure/scripts/federate-workload-identity.sh (Microsoft Graph, not ARM).

targetScope = 'resourceGroup'

@description('Short environment name: dev | staging | prod')
@allowed(['dev', 'staging', 'prod'])
param environmentName string

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Name prefix (lowercase letters/digits), e.g. acip')
@minLength(3)
@maxLength(10)
param prefix string = 'acip'

@description('Object id of the EXISTING collection service principal (Enterprise application object id, not the app registration id)')
param collectorPrincipalObjectId string

@description('PostgreSQL administrator login')
param postgresAdminLogin string = 'acipadmin'

@description('PostgreSQL administrator password (store in Key Vault after deployment; never commit)')
@secure()
param postgresAdminPassword string

@description('Enable zone-redundant high availability for PostgreSQL (recommended for prod)')
param postgresHighAvailability bool = false

@description('PostgreSQL SKU')
param postgresSkuName string = 'Standard_D2ds_v5'

@description('Use private networking (VNet-integrated PostgreSQL, private DNS). When false, public access with firewall rules is used.')
param privateNetworking bool = true

@description('Client IP ranges allowed to PostgreSQL when privateNetworking = false (e.g. AKS egress IP)')
param postgresAllowedIpRanges array = []

@description('AKS system node pool VM size')
param aksSystemVmSize string = 'Standard_D4ds_v5'

@description('AKS user node pool VM size')
param aksUserVmSize string = 'Standard_D4ds_v5'

@description('AKS user node pool autoscaler bounds')
param aksUserMinCount int = 2
param aksUserMaxCount int = 5

@description('Kubernetes version (empty = AKS default)')
param kubernetesVersion string = ''

@description('Name of the blob container receiving Cost Management exports')
param exportContainerName string = 'cost-exports'

@description('Tags applied to every resource')
param tags object = {}

var suffix = uniqueString(resourceGroup().id, prefix, environmentName)
var baseTags = union(tags, { application: 'acip', environment: environmentName })

module network 'modules/network.bicep' = if (privateNetworking) {
  name: 'network'
  params: {
    name: '${prefix}-${environmentName}-vnet'
    location: location
    tags: baseTags
  }
}

module logs 'modules/loganalytics.bicep' = {
  name: 'loganalytics'
  params: {
    name: '${prefix}-${environmentName}-law'
    location: location
    tags: baseTags
    retentionInDays: environmentName == 'prod' ? 90 : 30
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    name: toLower('${prefix}${environmentName}${take(suffix, 6)}')
    location: location
    tags: baseTags
    sku: environmentName == 'prod' ? 'Premium' : 'Standard'
  }
}

module aks 'modules/aks.bicep' = {
  name: 'aks'
  params: {
    name: '${prefix}-${environmentName}-aks'
    location: location
    tags: baseTags
    kubernetesVersion: kubernetesVersion
    systemVmSize: aksSystemVmSize
    userVmSize: aksUserVmSize
    userMinCount: aksUserMinCount
    userMaxCount: aksUserMaxCount
    logAnalyticsWorkspaceId: logs.outputs.id
    acrId: acr.outputs.id
    subnetId: privateNetworking ? network!.outputs.aksSubnetId : ''
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: toLower('${prefix}${environmentName}${take(suffix, 8)}')
    location: location
    tags: baseTags
    containerName: exportContainerName
    readerPrincipalObjectId: collectorPrincipalObjectId
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    name: '${prefix}-${environmentName}-${take(suffix, 6)}'
    location: location
    tags: baseTags
    vaultReaderPrincipalObjectId: collectorPrincipalObjectId
    purgeProtection: environmentName == 'prod'
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: '${prefix}-${environmentName}-pg-${take(suffix, 6)}'
    location: location
    tags: baseTags
    administratorLogin: postgresAdminLogin
    administratorPassword: postgresAdminPassword
    skuName: postgresSkuName
    highAvailability: postgresHighAvailability
    delegatedSubnetId: privateNetworking ? network!.outputs.postgresSubnetId : ''
    privateDnsZoneId: privateNetworking ? network!.outputs.postgresDnsZoneId : ''
    allowedIpRanges: postgresAllowedIpRanges
    backupRetentionDays: environmentName == 'prod' ? 35 : 7
  }
}

output acrLoginServer string = acr.outputs.loginServer
output aksName string = aks.outputs.name
output aksOidcIssuerUrl string = aks.outputs.oidcIssuerUrl
output storageAccountUrl string = storage.outputs.blobEndpoint
output storageAccountId string = storage.outputs.id
output keyVaultName string = keyVault.outputs.name
output postgresFqdn string = postgres.outputs.fqdn
output logAnalyticsWorkspaceId string = logs.outputs.id
