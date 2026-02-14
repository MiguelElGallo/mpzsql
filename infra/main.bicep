@description('Short environment name used in resource naming.')
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Storage account SKU.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
  'Standard_RAGRS'
])
param storageSkuName string = 'Standard_LRS'

@description('PostgreSQL administrator login (password auth).')
param postgresAdminLogin string = 'pgadmin'

@secure()
@description('PostgreSQL administrator password (password auth).')
param postgresAdminPassword string

@description('PostgreSQL compute SKU name.')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL compute tier.')
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param postgresSkuTier string = 'Burstable'

@description('PostgreSQL engine version.')
@allowed([
  '14'
  '15'
  '16'
  '17'
])
param postgresVersion string = '16'

@description('PostgreSQL data storage size in GB.')
param postgresStorageSizeGb int = 128

@description('Application database name.')
param postgresDatabaseName string = 'appdb'

@description('Object ID for the Microsoft Entra administrator of PostgreSQL.')
param postgresEntraAdminObjectId string

@description('Principal name (UPN/group/SPN display name) for PostgreSQL Entra admin sign-in.')
param postgresEntraAdminPrincipalName string

@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
@description('Principal type for PostgreSQL Entra admin.')
param postgresEntraAdminPrincipalType string = 'User'

@description('Container image for the Azure Container App.')
param containerAppImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('CPU cores for the container app as a numeric string (for example: 0.25, 0.5, 1.0).')
param containerCpu string = '0.5'

@description('Container memory setting.')
param containerMemory string = '1Gi'

@description('DuckLake data path for Azure Storage (e.g. az://lakehouse/data/).')
param ducklakeDataPath string = 'az://lakehouse/data/'

@secure()
@description('Auto-generated Flight SQL password. Random on each fresh provision.')
param lakehousePassword string = newGuid()

var uniqueSuffix = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var storageAccountName = 'st${uniqueSuffix}'
var postgresServerName = toLower('psql-${environmentName}-${substring(uniqueSuffix, 0, 6)}')
var containerAppsEnvironmentName = 'cae-${environmentName}'
var containerAppName = 'ca-${environmentName}'
var containerAppIdentityName = 'id-ca-${environmentName}'
var acrName = 'acr${uniqueSuffix}'
var keyVaultName = 'kv-${substring(uniqueSuffix, 0, 10)}'

// ── Managed Identity (standalone — breaks ACR ↔ Container App cycle) ────
resource containerAppIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: containerAppIdentityName
  location: location
}

module storage './modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: storageAccountName
    storageSkuName: storageSkuName
  }
}

module postgres './modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    location: location
    postgresServerName: postgresServerName
    postgresAdminLogin: postgresAdminLogin
    postgresAdminPassword: postgresAdminPassword
    postgresSkuName: postgresSkuName
    postgresSkuTier: postgresSkuTier
    postgresVersion: postgresVersion
    postgresStorageSizeGb: postgresStorageSizeGb
    postgresDatabaseName: postgresDatabaseName
    postgresEntraAdminObjectId: postgresEntraAdminObjectId
    postgresEntraAdminPrincipalName: postgresEntraAdminPrincipalName
    postgresEntraAdminPrincipalType: postgresEntraAdminPrincipalType
  }
}

module keyvault './modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    keyVaultName: keyVaultName
    containerAppPrincipalId: containerAppIdentity.properties.principalId
    deployerPrincipalId: postgresEntraAdminObjectId
    lakehousePassword: lakehousePassword
  }
}

module acr './modules/acr.bicep' = {
  name: 'acr'
  params: {
    location: location
    acrName: acrName
    pullPrincipalId: containerAppIdentity.properties.principalId
  }
}

module containerApp './modules/container-app.bicep' = {
  name: 'containerApp'
  params: {
    location: location
    containerAppsEnvironmentName: containerAppsEnvironmentName
    containerAppName: containerAppName
    containerAppIdentityId: containerAppIdentity.id
    containerAppIdentityName: containerAppIdentityName
    containerAppIdentityClientId: containerAppIdentity.properties.clientId
    containerAppImage: containerAppImage
    containerCpu: containerCpu
    containerMemory: containerMemory
    storageAccountName: storage.outputs.storageAccountName
    postgresFqdn: postgres.outputs.postgresFqdn
    postgresDatabaseName: postgres.outputs.postgresDatabaseName
    ducklakeDataPath: ducklakeDataPath
    acrLoginServer: acr.outputs.acrLoginServer
    lakehousePasswordSecretUri: keyvault.outputs.lakehousePasswordSecretUri
  }
}

resource storageAccountExisting 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource storageBlobDataContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountName, containerAppIdentityName, 'StorageBlobDataContributor')
  scope: storageAccountExisting
  dependsOn: [storage]
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalId: containerAppIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output STORAGE_ACCOUNT_NAME string = storage.outputs.storageAccountName
output STORAGE_ACCOUNT_ID string = storage.outputs.storageAccountId
output POSTGRES_SERVER_NAME string = postgres.outputs.postgresServerName
output POSTGRES_FQDN string = postgres.outputs.postgresFqdn
output POSTGRES_DATABASE_NAME string = postgres.outputs.postgresDatabaseName
output CONTAINER_APP_NAME string = containerApp.outputs.containerAppName
output CONTAINER_APP_IDENTITY_NAME string = containerAppIdentityName
output CONTAINER_APP_IDENTITY_CLIENT_ID string = containerAppIdentity.properties.clientId
output CONTAINER_APP_IDENTITY_PRINCIPAL_ID string = containerAppIdentity.properties.principalId
output ACR_NAME string = acr.outputs.acrName
output ACR_LOGIN_SERVER string = acr.outputs.acrLoginServer
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.acrLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.acrName
output KEY_VAULT_NAME string = keyvault.outputs.keyVaultName
output KEY_VAULT_URI string = keyvault.outputs.keyVaultUri
