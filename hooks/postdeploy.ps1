# Post-deploy hook (Windows / pwsh): smoke-checks the demo site and prints the agent endpoints.
$ErrorActionPreference = 'Continue'

$envValues = @{}
azd env get-values 2>$null | ForEach-Object { if ($_ -match '^([^=]+)="(.*)"$') { $envValues[$Matches[1]] = $Matches[2] } }

$site = $envValues['DEMO_SITE_URL']
if ($site) {
    try {
        $health = Invoke-RestMethod -Uri "$site/healthz" -TimeoutSec 60
        Write-Host "Demo site healthy: $site (status=$($health.status))"
    } catch {
        Write-Warning "Demo site not responding yet at $site/healthz (cold start or not deployed): $($_.Exception.Message)"
    }
}

foreach ($k in $envValues.Keys | Where-Object { $_ -match '^AGENT_.*_(NAME|VERSION|RESPONSES_ENDPOINT)$' } | Sort-Object) {
    Write-Host ("{0} = {1}" -f $k, $envValues[$k])
}

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $python) {
    Write-Host "Ensuring the prompt agent exists (Browser Automation tool)..."
    Push-Location $root
    & $python -m demo_cli agents ensure
    Pop-Location
} else {
    Write-Host "Tip: create the Python venv (see README) and run 'python -m demo_cli agents ensure' to create the prompt agent."
}
