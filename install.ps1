# VibeTune installer for Windows (PowerShell 5.1+ / PowerShell 7+)
# Usage:
#   irm https://raw.githubusercontent.com/ashrafpy/vibetune/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

try {
    $TlsProtocol = [Net.SecurityProtocolType]::Tls12
    if ([Enum]::GetNames([Net.SecurityProtocolType]) -contains "Tls13") {
        $TlsProtocol = $TlsProtocol -bor [Net.SecurityProtocolType]::Tls13
    }
    [Net.ServicePointManager]::SecurityProtocol = $TlsProtocol
} catch {
    # Ignore if platform restricts SecurityProtocol mutation
}

$Repo = if ($env:VIBETUNE_REPO) { $env:VIBETUNE_REPO } else { "ashrafpy/vibetune" }
$Ref = if ($env:VIBETUNE_REF) { $env:VIBETUNE_REF } else { "main" }
$SourceOverride = $env:VIBETUNE_SOURCE
$NoPlayer = if ($env:VIBETUNE_NO_PLAYER) { $env:VIBETUNE_NO_PLAYER } else { "0" }
$BinDir = if ($env:VIBETUNE_BIN_DIR) { $env:VIBETUNE_BIN_DIR } else { Join-Path $env:USERPROFILE ".local\bin" }

function Find-UvBinary {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Add-ToUserPath {
    param([string]$DirPath)
    if (-not $DirPath) {
        return
    }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if ($userPath) {
        $entries = $userPath.Split(";") | Where-Object { $_ -and $_.Trim() -ne "" }
    }
    $normalizedTarget = $DirPath.TrimEnd("\")
    $alreadyPresent = $false
    foreach ($entry in $entries) {
        if ($entry.TrimEnd("\").Equals($normalizedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
            $alreadyPresent = $true
            break
        }
    }
    if (-not $alreadyPresent) {
        $newUserPath = if ($entries.Count -gt 0) { ($entries + $DirPath) -join ";" } else { $DirPath }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }

    $procEntries = $env:PATH.Split(";")
    $inProc = $false
    foreach ($entry in $procEntries) {
        if ($entry.TrimEnd("\").Equals($normalizedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
            $inProc = $true
            break
        }
    }
    if (-not $inProc) {
        $env:PATH = "$DirPath;$env:PATH"
    }
}

Write-Host "Installing VibeTune for Windows..."

$UvBin = Find-UvBinary
if (-not $UvBin) {
    Write-Host "Installing uv (Python package & tool manager)..."
    Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" | Invoke-Expression
    $env:PATH = "$(Join-Path $env:USERPROFILE '.local\bin');$(Join-Path $env:USERPROFILE '.cargo\bin');$env:PATH"
    $UvBin = Find-UvBinary
    if (-not $UvBin) {
        throw "uv installation completed, but uv.exe could not be found."
    }
}

$PkgSource = if ($SourceOverride) { $SourceOverride } else { "https://github.com/$Repo/archive/$Ref.tar.gz" }

Write-Host "Installing vibetune CLI via uv..."
& $UvBin tool install --force --python ">=3.11" $PkgSource
if ($LASTEXITCODE -ne 0) {
    throw "uv tool install failed with exit code $LASTEXITCODE"
}

try {
    & $UvBin tool update-shell | Out-Null
} catch {
    # Non-fatal if shell profile update is unavailable
}

$ToolBinDir = if ($env:UV_TOOL_BIN_DIR) { $env:UV_TOOL_BIN_DIR } else { Join-Path $env:USERPROFILE ".local\bin" }
Add-ToUserPath -DirPath $ToolBinDir
if ($BinDir -ne $ToolBinDir) {
    Add-ToUserPath -DirPath $BinDir
}

if ($NoPlayer -eq "1") {
    Write-Host "Skipping optional go-librespot local audio engine (VIBETUNE_NO_PLAYER=1)."
} else {
    $existingPlayer = Get-Command go-librespot -ErrorAction SilentlyContinue
    $targetPlayer = Join-Path $BinDir "go-librespot.exe"
    if ($existingPlayer -or (Test-Path $targetPlayer)) {
        Write-Host "go-librespot is already installed; keeping existing binary."
    } else {
        $tarExe = Get-Command tar.exe -ErrorAction SilentlyContinue
        if (-not $tarExe) {
            Write-Warning "tar.exe not found; skipping optional go-librespot download. VibeTune still works in --remote-only mode."
        } else {
            $assetUrl = "https://github.com/devgianlu/go-librespot/releases/latest/download/go-librespot_windows_amd64.tar.gz"
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("vibetune-" + [System.Guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                Write-Host "Installing optional local audio engine (go-librespot for Windows)..."
                $archivePath = Join-Path $tempDir "go-librespot.tar.gz"
                Invoke-WebRequest -Uri $assetUrl -OutFile $archivePath -UseBasicParsing
                & $tarExe.Source -xzf $archivePath -C $tempDir
                if ($LASTEXITCODE -ne 0) {
                    throw "tar extraction failed with exit code $LASTEXITCODE"
                }
                $extractedExe = Join-Path $tempDir "go-librespot.exe"
                if (-not (Test-Path $extractedExe)) {
                    throw "go-librespot.exe was not found in the downloaded archive."
                }
                New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
                Copy-Item -Path $extractedExe -Destination $targetPlayer -Force
                Write-Host "Installed go-librespot.exe to $targetPlayer"
            } catch {
                Write-Warning "Could not install optional go-librespot.exe ($($_.Exception.Message)). VibeTune still works in --remote-only mode."
            } finally {
                if (Test-Path $tempDir) {
                    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

$VibeTuneExe = Join-Path $ToolBinDir "vibetune.exe"
if (-not (Test-Path $VibeTuneExe)) {
    $cmdVt = Get-Command vibetune -ErrorAction SilentlyContinue
    if ($cmdVt) {
        $VibeTuneExe = $cmdVt.Source
    }
}

Write-Host ""
if ($VibeTuneExe -and (Test-Path $VibeTuneExe)) {
    $ver = & $VibeTuneExe --version 2>$null
    Write-Host "Successfully installed $ver at $VibeTuneExe"
} else {
    Write-Warning "VibeTune was installed, but vibetune.exe was not found in PATH yet. Restart your terminal."
}

Write-Host ""
Write-Host "Next steps (Windows Terminal recommended for TrueColor & Unicode Sextant art):"
Write-Host "  1. Configure Spotify API keys:  vibetune --setup"
Write-Host "  2. (Optional) Local audio auth: vibetune --auth-player"
Write-Host "  3. Launch VibeTune:             vibetune"
