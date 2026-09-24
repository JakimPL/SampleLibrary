$ErrorActionPreference = "SilentlyContinue"
try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/setup/quit" -TimeoutSec 10 | Out-Null
} catch {
}
$installation = Join-Path $env:LOCALAPPDATA "pyapp\data\samplelibrary"
$deadline = (Get-Date).AddSeconds(60)
do {
    $running = @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($installation, [StringComparison]::OrdinalIgnoreCase) })
    if ($running.Count -eq 0) {
        exit 0
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
$running | Stop-Process -Force
