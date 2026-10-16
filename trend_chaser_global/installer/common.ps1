# Pure package/filesystem operations, shared with cross-platform installer checks.
function Safe-Relative([string]$Rel) {
    if ([IO.Path]::IsPathRooted($Rel) -or $Rel.Contains('\') -or $Rel.Contains(':') -or $Rel -match '(^|/)(\.|\.\.|)($|/)' -or $Rel.EndsWith('/')) {
        throw 'Unsafe package path in manifest.'
    }
    return $Rel.Replace('/', [IO.Path]::DirectorySeparatorChar)
}

function Test-Bundle([string]$Source) {
    $Manifest = Get-Content -LiteralPath (Join-Path $Source 'manifest.json') -Raw | ConvertFrom-Json
    $Expected = @{}
    foreach ($Entry in $Manifest.files.PSObject.Properties) {
        $Rel = Safe-Relative $Entry.Name
        $File = Join-Path $Source $Rel
        if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw ('Missing package file: ' + $Entry.Name) }
        if ((Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.Value) { throw ('Checksum failed: ' + $Entry.Name) }
        $Expected[$Entry.Name] = $true
    }
    foreach ($File in Get-ChildItem -LiteralPath $Source -Recurse -File) {
        $Rel = $File.FullName.Substring($Source.Length + 1).Replace('\','/')
        if ($Rel -ne 'manifest.json' -and -not $Expected.ContainsKey($Rel)) { throw ('Unexpected package file: ' + $Rel) }
    }
}

function Assert-OwnedRoot([string]$Root) {
    $Marker = Join-Path $Root '.global-trend-owned'
    if (Test-Path -LiteralPath $Root) {
        if (-not (Test-Path -LiteralPath $Marker) -or (Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'Trend Chaser Global owned installation') {
            throw 'The target folder exists without this app ownership marker. Installation stopped to preserve its contents.'
        }
    }
}

function Swap-Program([string]$StagedProgram, [string]$Program, [string]$Backup) {
    if (Test-Path -LiteralPath $Program) { Move-Item -LiteralPath $Program -Destination $Backup }
    try { Move-Item -LiteralPath $StagedProgram -Destination $Program -ErrorAction Stop }
    catch {
        if (Test-Path -LiteralPath $Backup) { Move-Item -LiteralPath $Backup -Destination $Program }
        throw
    }
}

function Assert-OwnedShortcut([string]$Path, [string]$ExpectedTarget, $Shell) {
    if (Test-Path -LiteralPath $Path) {
        $Link = $Shell.CreateShortcut($Path)
        if (-not [String]::Equals($Link.TargetPath,$ExpectedTarget,[StringComparison]::OrdinalIgnoreCase)) {
            throw ('An unrelated shortcut already exists: ' + $Path + '. Rename it before installing.')
        }
    }
}

function Backup-IntegrationFiles([string[]]$Paths,[string]$Folder) {
    New-Item -ItemType Directory -Path $Folder -Force | Out-Null
    $Records = @()
    foreach ($Path in $Paths) {
        $Exists = Test-Path -LiteralPath $Path
        if ($Exists -and -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'Integration path is not a regular file.' }
        $Copy = Join-Path $Folder ([string]$Records.Count)
        if ($Exists) { Copy-Item -LiteralPath $Path -Destination $Copy -ErrorAction Stop }
        $Records += [PSCustomObject]@{Path=$Path;Existed=$Exists;Backup=$Copy}
    }
    return $Records
}

function Restore-IntegrationFiles($Records) {
    foreach ($Record in $Records) {
        if ($Record.Existed) { Copy-Item -LiteralPath $Record.Backup -Destination $Record.Path -Force -ErrorAction Stop }
        elseif (Test-Path -LiteralPath $Record.Path) { Remove-Item -LiteralPath $Record.Path -Force -ErrorAction Stop }
    }
}
