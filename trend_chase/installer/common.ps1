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
    $Marker = Join-Path $Root '.trend-chase-v1-owned'
    if (Test-Path -LiteralPath $Root) {
        if (-not (Test-Path -LiteralPath $Marker) -or (Get-Content -LiteralPath $Marker -Raw).Trim() -ne 'Trend Chase Version 1 owned installation') {
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
