// Returns the containers of an existing container app, so re-provisioning keeps the image deployed by `azd deploy`
// instead of resetting it to the placeholder.
param exists bool
param name string

resource existingApp 'Microsoft.App/containerApps@2024-03-01' existing = if (exists) {
  name: name
}

output containers array = exists ? existingApp!.properties.template.containers : []
