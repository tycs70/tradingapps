$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '..\installer\common.ps1')
function Assert([bool]$Value,[string]$Message) { if (-not $Value) { throw $Message } }
function Must-Throw([scriptblock]$Action) {
    $Failed = $false
    try { & $Action } catch { $Failed = $true }
    Assert $Failed 'Expected operation to reject unsafe/corrupt input.'
}
$Temp = Join-Path ([IO.Path]::GetTempPath()) ("Global test ' " + [char]0x0394 + ' ' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $Temp | Out-Null
    foreach ($Path in @('../x','/tmp/x','C:/x','a/../../x','a\b','a//b')) { Must-Throw { Safe-Relative $Path } }
    $Root = Join-Path $Temp 'owned root'
    Assert-OwnedRoot $Root
    New-Item -ItemType Directory -Path $Root | Out-Null
    Must-Throw { Assert-OwnedRoot $Root }
    Set-Content -LiteralPath (Join-Path $Root '.global-trend-owned') -Value 'Trend Chaser Global owned installation'
    Assert-OwnedRoot $Root
    $Data = Join-Path $Root 'data'
    New-Item -ItemType Directory -Path $Data | Out-Null
    Set-Content -LiteralPath (Join-Path $Data 'settings.json') -Value 'preserved'
    $Program = Join-Path $Root 'program'
    New-Item -ItemType Directory -Path $Program | Out-Null
    Set-Content -LiteralPath (Join-Path $Program 'old.txt') -Value 'old'
    $Stage = Join-Path $Root 'stage'
    New-Item -ItemType Directory -Path $Stage | Out-Null
    Set-Content -LiteralPath (Join-Path $Stage 'new.txt') -Value 'new'
    $Backup = Join-Path $Root 'backup'
    Swap-Program $Stage $Program $Backup
    Assert (Test-Path -LiteralPath (Join-Path $Program 'new.txt')) 'Staged program was not applied.'
    Assert ((Get-Content -LiteralPath (Join-Path $Data 'settings.json')).Trim() -eq 'preserved') 'Data was lost during swap.'
    Remove-Item -LiteralPath $Backup -Recurse
    Must-Throw { Swap-Program (Join-Path $Root 'missing') $Program $Backup }
    Assert (Test-Path -LiteralPath (Join-Path $Program 'new.txt')) 'Failed staging did not restore previous program.'
    $Bundle = Join-Path $Temp 'bundle'
    New-Item -ItemType Directory -Path $Bundle | Out-Null
    $File = Join-Path $Bundle 'x.txt'
    Set-Content -LiteralPath $File -Value 'original'
    $Hash = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
    @{files=@{'x.txt'=$Hash}} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Bundle 'manifest.json')
    Test-Bundle $Bundle
    Set-Content -LiteralPath $File -Value 'corrupt'
    Must-Throw { Test-Bundle $Bundle }
    Write-Host 'Installer filesystem checks passed: quoted/Unicode paths, ownership, safe swap, rollback, preserved data, corruption.'
} finally { if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force } }
