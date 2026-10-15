$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Source = $PSScriptRoot
. (Join-Path $Source 'common.ps1')
$Root = Join-Path $env:LOCALAPPDATA 'Trend_Chaser_Global'
$Program = Join-Path $Root 'program'
$Data = Join-Path $Root 'data'
$Marker = Join-Path $Root '.global-trend-owned'
$Stage = Join-Path $Root ('.stage-' + [guid]::NewGuid().ToString('N'))
$Backup = Join-Path $Root ('.backup-' + [guid]::NewGuid().ToString('N'))
$RegPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Trend_Chaser_Global'
$DesktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Trend Chaser Global.lnk'
$MenuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Trend Chaser Global'
$LockStream = $null
$InstallGuard = $null
$Swapped = $false
$Committed = $false
$HadProgram = Test-Path -LiteralPath $Program
$HadDesktop = Test-Path -LiteralPath $DesktopLink
$HadMenu = Test-Path -LiteralPath $MenuDir
$HadRegistry = Test-Path -LiteralPath $RegPath
$Log = Join-Path $env:TEMP ('Trend-Chaser-Global-install-' + [guid]::NewGuid().ToString('N') + '.log')

try {
    Start-Transcript -Path $Log | Out-Null
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw 'This installer requires Windows 10/11 on an Intel/AMD 64-bit laptop.'
    }
    if ([Environment]::OSVersion.Version.Major -lt 10) { throw 'Windows 10 or newer is required.' }
    Write-Host 'Verifying every bundled file...'
    Test-Bundle $Source
    Assert-OwnedRoot $Root
    New-Item -ItemType Directory -Path $Root,$Data -Force | Out-Null
    Set-Content -LiteralPath $Marker -Value 'Trend Chaser Global owned installation' -Encoding UTF8
    $InstallGuard = [IO.File]::Open((Join-Path $Root 'install.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
        $LockStream = [IO.File]::Open((Join-Path $Data 'global.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    } catch { throw 'The app is running. Close Trend Chaser Global and retry.' }
    New-Item -ItemType Directory -Path $Stage -Force | Out-Null
    $StagedProgram = Join-Path $Stage 'program'
    New-Item -ItemType Directory -Path $StagedProgram -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $Source 'app') -Destination $StagedProgram -Recurse
    $Runtime = Join-Path $StagedProgram 'runtime'
    Expand-Archive -LiteralPath (Join-Path $Source 'runtime.zip') -DestinationPath $Runtime
    $Python = Join-Path $Runtime 'python.exe'
    $env:TCL_LIBRARY = Join-Path $Runtime 'tcl\tcl8.6'
    $env:TK_LIBRARY = Join-Path $Runtime 'tcl\tk8.6'
    Write-Host 'Installing bundled, pinned dependencies offline...'
    & $Python -E -s -m pip install --no-index --disable-pip-version-check --no-warn-script-location --find-links (Join-Path $Source 'wheels') --require-hashes -r (Join-Path $Source 'requirements-windows.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Offline dependency installation failed.' }
    & $Python -E -s (Join-Path $StagedProgram 'app\verify_install.py')
    if ($LASTEXITCODE -ne 0) { throw 'The offline Python/Tk startup check failed.' }
    Write-Host 'Creating the Desktop and Start Menu shortcuts...'
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut((Join-Path $Stage 'app.lnk'))
    $Shortcut.TargetPath = Join-Path $Program 'runtime\pythonw.exe'
    $Shortcut.Arguments = '-E -s "' + (Join-Path $Program 'app\run_app.pyw') + '"'
    $Shortcut.WorkingDirectory = Join-Path $Program 'app'
    $Shortcut.Description = 'EMA9/EMA21 cTrader demo trend ranking'
    $Shortcut.IconLocation = (Join-Path $Program 'app\assets\icon.ico') + ',0'
    $Shortcut.Save()
    Swap-Program $StagedProgram $Program $Backup
    $Swapped = $true
    New-Item -ItemType Directory -Path $MenuDir -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $Stage 'app.lnk') -Destination $DesktopLink -Force
    Copy-Item -LiteralPath (Join-Path $Stage 'app.lnk') -Destination (Join-Path $MenuDir 'Trend Chaser Global.lnk') -Force
    $DemoShortcut = $Shell.CreateShortcut((Join-Path $MenuDir 'Trend Chaser Global - Offline Sample.lnk'))
    $DemoShortcut.TargetPath = $Shortcut.TargetPath
    $DemoShortcut.Arguments = $Shortcut.Arguments + ' --demo'
    $DemoShortcut.WorkingDirectory = $Shortcut.WorkingDirectory
    $DemoShortcut.IconLocation = $Shortcut.IconLocation
    $DemoShortcut.Description = 'Fictional offline sample - no market connection'
    $DemoShortcut.Save()
    Copy-Item -LiteralPath (Join-Path $Source 'uninstall.ps1') -Destination (Join-Path $Root 'uninstall.ps1') -Force
    New-Item -Path $RegPath -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name DisplayName -Value 'Trend Chaser Global' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name DisplayVersion -Value '1.0.0' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name Publisher -Value 'TradingApps' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name InstallLocation -Value $Root -PropertyType String -Force | Out-Null
    $UninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Root 'uninstall.ps1') + '"'
    New-ItemProperty -Path $RegPath -Name UninstallString -Value $UninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
    Set-Content -LiteralPath $Marker -Value 'Trend Chaser Global owned installation' -Encoding UTF8
    $Committed = $true
    Write-Host ('Installed into ' + $Root)
    Write-Host 'Your new Desktop shortcut is ready. Settings and logs have been preserved.'
} catch {
    Write-Host ('Installation failed: ' + $_.Exception.Message) -ForegroundColor Red
    if ($Swapped -and -not $Committed) {
        if (Test-Path -LiteralPath $Program) { Remove-Item -LiteralPath $Program -Recurse -Force }
    }
    if (-not $Committed -and (Test-Path -LiteralPath $Backup)) { Move-Item -LiteralPath $Backup -Destination $Program }
    if (-not $Committed -and -not $HadDesktop -and (Test-Path -LiteralPath $DesktopLink)) { Remove-Item -LiteralPath $DesktopLink -Force }
    if (-not $Committed -and -not $HadMenu -and (Test-Path -LiteralPath $MenuDir)) { Remove-Item -LiteralPath $MenuDir -Recurse -Force }
    if (-not $Committed -and -not $HadRegistry -and (Test-Path -LiteralPath $RegPath)) { Remove-Item -LiteralPath $RegPath -Recurse -Force }
    Write-Host ('Installation log: ' + $Log)
    exit 1
} finally {
    if ($LockStream) { $LockStream.Dispose() }
    if ($InstallGuard) { $InstallGuard.Dispose() }
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
    if ($Committed -and (Test-Path -LiteralPath $Backup)) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    try { Stop-Transcript | Out-Null } catch { }
}
