# Loads the azd environment of a project folder into the current PowerShell session so the demo CLI
# targets it (process environment variables take precedence over the repo .env file).
# Usage:  . .\scripts\use-azd-env.ps1 -ProjectDir C:\dev\other-copy [-Credential AzureCliCredential]
param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [string]$Credential = ''
)
Push-Location $ProjectDir
try {
    azd env get-values | ForEach-Object {
        if ($_ -match '^([^=]+)="(.*)"$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] }
    }
} finally { Pop-Location }
if ($Credential) { $env:AZURE_TOKEN_CREDENTIALS = $Credential }
Write-Host "Loaded azd environment '$env:AZURE_ENV_NAME' -> $env:FOUNDRY_PROJECT_ENDPOINT"
