// Reads the Foundry project created by the foundry layer (no changes are made here).
targetScope = 'resourceGroup'

param foundryAccountName string
param foundryProjectName string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName

  resource project 'projects' existing = {
    name: foundryProjectName
  }
}

output projectPrincipalId string = account::project.identity.principalId
output projectId string = account::project.id
output accountId string = account.id
