param name string
param location string
param tags object
param administratorLogin string
@secure()
param administratorPassword string
param skuName string = 'Standard_D2ds_v5'
param highAvailability bool = false
param storageSizeGB int = 128
param backupRetentionDays int = 7
@description('Delegated subnet (private access). Empty = public access + firewall rules.')
param delegatedSubnetId string = ''
param privateDnsZoneId string = ''
param allowedIpRanges array = []
param databaseName string = 'acip'

var isPrivate = !empty(delegatedSubnetId)

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: skuName, tier: 'GeneralPurpose' }
  properties: {
    version: '16'
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    storage: { storageSizeGB: storageSizeGB, autoGrow: 'Enabled' }
    backup: { backupRetentionDays: backupRetentionDays, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: highAvailability ? 'ZoneRedundant' : 'Disabled' }
    network: isPrivate
      ? { delegatedSubnetResourceId: delegatedSubnetId, privateDnsZoneArmResourceId: privateDnsZoneId, publicNetworkAccess: 'Disabled' }
      : { publicNetworkAccess: 'Enabled' }
    authConfig: { activeDirectoryAuth: 'Enabled', passwordAuth: 'Enabled' }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// TLS is mandatory for every connection
resource tls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: pg
  name: 'require_secure_transport'
  properties: { value: 'ON', source: 'user-override' }
}

resource fw 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = [for (r, i) in allowedIpRanges: if (!isPrivate) {
  parent: pg
  name: 'allow-${i}'
  properties: { startIpAddress: r.start, endIpAddress: r.end }
}]

output fqdn string = pg.properties.fullyQualifiedDomainName
output name string = pg.name
