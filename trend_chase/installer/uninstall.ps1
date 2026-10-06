param([switch]$RemoveData)
$ErrorActionPreference = 'Stop'
$Root = Join-Path $env:LOCALAPPDATA 'Trend_Chase_V1'
$Marker = Join-Path $Root '.trend-chase-v1-owned'
if ($PSScriptRoot -ne $Root -or -not (Test-Path -LiteralPath $Marker) -or
    (Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'Trend Chase Version 1 owned installation') {
    throw 'This uninstaller only removes its own installed application.'
}
$Guard = $null
$Lock = $null
try {
    $Guard = [IO.File]::Open((Join-Path $Root 'install.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $Lock = [IO.File]::Open((Join-Path $Root 'data\instance.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $Program = Join-Path $Root 'program'
    if (Test-Path -LiteralPath $Program) { Remove-Item -LiteralPath $Program -Recurse -Force }
    $DesktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Trend Chase Version 1.lnk'
    if (Test-Path -LiteralPath $DesktopLink) { Remove-Item -LiteralPath $DesktopLink -Force }
    $Menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Trend Chase Version 1'
    if (Test-Path -LiteralPath $Menu) { Remove-Item -LiteralPath $Menu -Recurse -Force }
    $Reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Trend_Chase_V1'
    if (Test-Path -LiteralPath $Reg) { Remove-Item -LiteralPath $Reg -Recurse -Force }
    Write-Host 'Trend Chase Version 1 removed. Settings and logs are retained for a future reinstall.'
} catch {
    Write-Host ('Uninstall stopped: ' + $_.Exception.Message + '. Close the app before uninstalling.') -ForegroundColor Red
    exit 1
} finally {
    if ($Lock) { $Lock.Dispose() }
    if ($Guard) { $Guard.Dispose() }
}
if ($RemoveData) { Remove-Item -LiteralPath $Root -Recurse -Force }
