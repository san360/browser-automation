// Azure Playwright Workspace (Azure App Testing) that provides the cloud browsers used by the
// Foundry Browser Automation tool, plus the RBAC the project identity needs to start sessions.
targetScope = 'resourceGroup'

param location string
param tags object
param workspaceName string

@allowed([
  'Enabled'
  'Disabled'
])
param localAuth string = 'Disabled'

@description('Principal ID of the Foundry project system-assigned managed identity.')
param foundryProjectPrincipalId string

@description('Optional developer principal that also gets workspace access (for local raw-Playwright experiments).')
param developerPrincipalId string = ''
param developerPrincipalType string = 'User'

// Built-in role: Playwright Workspace Contributor (start browser sessions, manage own tokens).
var playwrightWorkspaceContributorRoleId = '78cf819f-0969-4ebe-8759-015c6efcd5bf'

resource workspace 'Microsoft.LoadTestService/playwrightWorkspaces@2025-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    regionalAffinity: 'Enabled'
    localAuth: localAuth
  }
}

resource projectRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workspace.id, foundryProjectPrincipalId, playwrightWorkspaceContributorRoleId)
  scope: workspace
  properties: {
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', playwrightWorkspaceContributorRoleId)
  }
}

resource developerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(workspace.id, developerPrincipalId, playwrightWorkspaceContributorRoleId)
  scope: workspace
  properties: {
    principalId: developerPrincipalId
    principalType: developerPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', playwrightWorkspaceContributorRoleId)
  }
}

// dataplaneUri looks like https://<region>.api.playwright.microsoft.com/playwrightworkspaces/<workspace-id>
var dataplaneUri = workspace.properties.dataplaneUri

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output dataplaneUri string = dataplaneUri
output browserEndpoint string = '${replace(dataplaneUri, 'https://', 'wss://')}/browsers'
