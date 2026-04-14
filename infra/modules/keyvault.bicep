@description('Azure region for the Key Vault.')
param location string

@description('Name of the Key Vault.')
param keyVaultName string

@description('Principal ID of the container app managed identity (gets Secrets User).')
param containerAppPrincipalId string

@description('Principal ID of the deployer (gets Secrets User to read password for testing). Empty string skips the assignment.')
param deployerPrincipalId string = ''

@secure()
@description('Flight SQL password to store in the vault.')
param lakehousePassword string

@secure()
@description('Flight SQL HMAC/JWT signing key to store in the vault.')
param lakehouseSecretKey string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// ── Role: Key Vault Secrets User → container app identity (read secrets) ──
resource secretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerAppPrincipalId, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
    )
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ── Role: Key Vault Secrets User → deployer (read secrets for testing) ─
resource deployerSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(keyVault.id, deployerPrincipalId, 'KeyVaultSecretsUser-deployer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
    )
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

// ── Secret: lakehouse-password ──────────────────────────────────────────
resource lakehousePasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'lakehouse-password'
  properties: {
    value: lakehousePassword
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

// ── Secret: lakehouse-secret-key ────────────────────────────────────────
resource lakehouseSecretKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'lakehouse-secret-key'
  properties: {
    value: lakehouseSecretKey
    contentType: 'text/plain'
    attributes: {
      enabled: true
    }
  }
}

output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri

// URI only (no secret value) — safe to expose for Container App Key Vault references.
#disable-next-line outputs-should-not-contain-secrets
output lakehousePasswordSecretUri string = lakehousePasswordSecret.properties.secretUri

// URI only (no secret value) — safe to expose for Container App Key Vault references.
#disable-next-line outputs-should-not-contain-secrets
output lakehouseSecretKeySecretUri string = lakehouseSecretKeySecret.properties.secretUri
