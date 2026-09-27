param([Parameter(Mandatory = $true)][string] $Executable)
$ErrorActionPreference = "SilentlyContinue"
$python = & $Executable self python-path
if ($python -and (Test-Path $python)) {
    & $python -m sampleripper.app --quit | Out-Null
}
$installation = Join-Path $env:LOCALAPPDATA "pyapp\data\sampleripper"
$deadline = (Get-Date).AddSeconds(60)
do {
    $running = @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($installation, [StringComparison]::OrdinalIgnoreCase) })
    if ($running.Count -eq 0) {
        exit 0
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
$running | Stop-Process -Force
