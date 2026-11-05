param name string
param location string
param tags object
@description('Principal allowed to read secrets (CSI driver via Workload Identity)')
param vaultReaderPrincipalObjectId string
param purgeProtection bool = true

var secretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: purgeProtection ? true : null
    publicNetworkAccess: 'Enabled'
  }
}

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, vaultReaderPrincipalObjectId, 'KeyVaultSecretsUser')
  scope: kv
  properties: {
    roleDefinitionId: secretsUserRoleId
    principalId: vaultReaderPrincipalObjectId
    principalType: 'ServicePrincipal'
  }
}

output id string = kv.id
output name string = kv.name
