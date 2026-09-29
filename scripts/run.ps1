<#
.SYNOPSIS
    Downloads and runs ytgrab without installing anything system-wide.

.DESCRIPTION
    This is the ONLY thing an end user needs to run:

        irm https://raw.githubusercontent.com/<owner>/ytgrab/main/scripts/run.ps1 | iex

    It does NOT install Python, FFmpeg or yt-dlp on your system, does NOT
    change PATH or the registry, and does NOT need Administrator rights.
    Everything it downloads goes into your own per-user folders:

      - %LOCALAPPDATA%\ytgrab\runtime   reusable cache (uv, Python, FFmpeg)
      - %TEMP%\ytgrab-run-<id>          this run's working copy, deleted after

    See the "How this works" and "Security" sections of README.md for the
    full explanation of what this script downloads and why.

.NOTES
    Requires PowerShell 5.1+ (built into Windows 10/11) and internet access.
    Safe to read before running: this script only talks to github.com (which
    redirects source-archive downloads to codeload.github.com and release-
    asset downloads to objects.githubusercontent.com) over HTTPS, and only
    writes inside your own user-profile folders. It does not call any
    GitHub API and does not require a GitHub Release to exist.
#>

[CmdletBinding()]
param(
    # Which version of ytgrab to run.
    #   "latest" (the default) fetches the current `main` branch directly
    #     from GitHub. This does NOT require a GitHub Release to exist.
    #   Anything else (e.g. "v1.0.0") is treated as a git tag and fetches
    #     that tag's archive instead, for pinning to an exact version.
    [string]$Version = "latest",

    # Delete the reusable runtime cache (uv, managed Python, FFmpeg) after
    # this run, instead of keeping it for faster future runs.
    [switch]$FullCleanup
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- Fixed, hardcoded sources (never built from user input) ----------------

$RepoOwner = "z3r0trace101-sudo"
$RepoName = "ytgrab"

# uv (Astral's Python package/venv manager). Pinned version + published
# per-release SHA256 file, both verified before the binary is ever run.
$UvVersion = "0.5.11"
$UvAsset = "uv-x86_64-pc-windows-msvc.zip"
$UvDownloadUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion/$UvAsset"
$UvChecksumUrl = "$UvDownloadUrl.sha256"

# Portable, statically-linked FFmpeg build for Windows. BtbN's builds are a
# widely used open-source source for this; see README's Security section for
# why this one download cannot be SHA256-verified against a maintainer hash
# (BtbN does not publish one) and what we check instead.
$FfmpegDownloadUrl =
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" +
    "ffmpeg-master-latest-win64-gpl.zip"

# --- Small helpers -----------------------------------------------------------

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Windows {
    if ($env:OS -ne "Windows_NT") {
        throw "ytgrab's run.ps1 only supports Windows 10/11."
    }
}

function New-RuntimePaths {
    $runtimeRoot = Join-Path $env:LOCALAPPDATA "ytgrab\runtime"
    [pscustomobject]@{
        RuntimeRoot = $runtimeRoot
        UvDir       = Join-Path $runtimeRoot "uv\$UvVersion"
        PythonDir   = Join-Path $runtimeRoot "python"
        FfmpegDir   = Join-Path $runtimeRoot "ffmpeg"
        CacheDir    = Join-Path $runtimeRoot "uv-cache"
        WorkDir     = Join-Path $env:TEMP ("ytgrab-run-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    }
}

function Invoke-HttpsDownload([string]$Url, [string]$Destination) {
    if ($Url -notlike "https://*") {
        throw "Refusing to download from a non-HTTPS URL: $Url"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

function Assert-FileSha256([string]$Path, [string]$ExpectedHex) {
    $actual = (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    if ($actual.ToLowerInvariant() -ne $ExpectedHex.ToLowerInvariant()) {
        Remove-Item $Path -Force -ErrorAction SilentlyContinue
        throw "Checksum mismatch for $Path. Expected $ExpectedHex, got $actual. Aborting."
    }
}

# --- Step 1: uv (the ephemeral Python/venv manager) -------------------------

function Get-Uv([string]$UvDir) {
    $uvExe = Join-Path $UvDir "uv.exe"
    if (Test-Path $uvExe) {
        return $uvExe
    }

    Write-Step "Fetching uv $UvVersion (manages an isolated Python for this app only)"
    $tempZip = Join-Path $env:TEMP "ytgrab-uv-$UvVersion.zip"
    $tempSha = "$tempZip.sha256"
    try {
        Invoke-HttpsDownload -Url $UvDownloadUrl -Destination $tempZip
        Invoke-HttpsDownload -Url $UvChecksumUrl -Destination $tempSha

        # uv's *.sha256 file is "<hex>  <filename>"; take the first token.
        $expected = (Get-Content $tempSha -Raw).Trim().Split(" ")[0]
        Assert-FileSha256 -Path $tempZip -ExpectedHex $expected

        New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
        Expand-Archive -Path $tempZip -DestinationPath $UvDir -Force
    }
    finally {
        Remove-Item $tempZip, $tempSha -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path $uvExe)) {
        throw "uv.exe was not found after extraction. The release layout may have changed."
    }
    return $uvExe
}

# --- Step 2: source code for the requested version ---------------------------

function Resolve-YtgrabArchiveUrl([string]$RequestedVersion) {
    # No GitHub Release, and no GitHub API call, is required for this to
    # work: "latest" always means "the current main branch", fetched as a
    # plain source archive straight from github.com. A specific tag (e.g.
    # "v1.0.0") fetches that tag's archive the same way.
    if ($RequestedVersion -eq "latest") {
        return "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/main.zip"
    }
    return "https://github.com/$RepoOwner/$RepoName/archive/refs/tags/$RequestedVersion.zip"
}

function Get-YtgrabSource([string]$RequestedVersion, [string]$WorkDir) {
    Write-Step "Downloading ytgrab source ($RequestedVersion)"
    $archiveUrl = Resolve-YtgrabArchiveUrl -RequestedVersion $RequestedVersion

    # A specific tag's archive is fixed by that tag/commit, which is the
    # practical equivalent of a checksum: re-tagging a release is a visible,
    # auditable action on GitHub. The default "latest" instead fetches the
    # current main branch, which is NOT pinned and can change between runs;
    # pass -Version with a tag once one exists for a stronger guarantee.
    $safeName = ($RequestedVersion -replace '[^A-Za-z0-9_.-]', '_')
    $zipPath = Join-Path $env:TEMP "ytgrab-src-$safeName.zip"
    try {
        Invoke-HttpsDownload -Url $archiveUrl -Destination $zipPath
        New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $WorkDir -Force
    }
    finally {
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    }

    $extracted = Get-ChildItem -Path $WorkDir -Directory | Select-Object -First 1
    if (-not $extracted) {
        throw "ytgrab source archive did not extract as expected."
    }
    return $extracted.FullName
}

# --- Step 3: FFmpeg (portable, never installed system-wide) ------------------

function Get-Ffmpeg([string]$FfmpegDir) {
    $ffmpegExe = Join-Path $FfmpegDir "ffmpeg.exe"
    if (Test-Path $ffmpegExe) {
        return $ffmpegExe
    }

    Write-Step "Fetching a portable FFmpeg build (used only by this app, not installed)"
    $tempZip = Join-Path $env:TEMP "ytgrab-ffmpeg.zip"
    try {
        Invoke-HttpsDownload -Url $FfmpegDownloadUrl -Destination $tempZip

        # BtbN does not publish a per-release checksum file, so a hash check
        # against a known-good value is not possible here (unlike the uv
        # download above). We still confirm the download is a well-formed
        # zip archive before trusting it, and everything happens over HTTPS
        # directly from GitHub's release storage.
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $archive = [System.IO.Compression.ZipFile]::OpenRead($tempZip)
            $archive.Dispose()
        }
        catch {
            throw "Downloaded FFmpeg archive is not a valid zip file. Aborting."
        }

        $extractDir = Join-Path $env:TEMP "ytgrab-ffmpeg-extract"
        Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $tempZip -DestinationPath $extractDir -Force

        $found = Get-ChildItem -Path $extractDir -Recurse -Filter "ffmpeg.exe" |
            Select-Object -First 1
        if (-not $found) {
            throw "ffmpeg.exe was not found inside the downloaded archive."
        }
        New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
        Copy-Item $found.FullName $ffmpegExe -Force
        Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    finally {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    }
    return $ffmpegExe
}

# --- Step 4: run ytgrab --------------------------------------------------------

function Start-Ytgrab([string]$UvExe, [string]$SourceDir, [string]$FfmpegExe, $Paths) {
    Write-Step "Starting ytgrab"

    # Scoped to this process only: no setx, no PATH edit, no registry write.
    $env:YTGRAB_FFMPEG = $FfmpegExe
    $env:UV_CACHE_DIR = $Paths.CacheDir
    $env:UV_PYTHON_INSTALL_DIR = $Paths.PythonDir
    # uv manages its own Python here; it never touches any system Python.
    $env:UV_PYTHON_PREFERENCE = "only-managed"

    Push-Location $SourceDir
    try {
        & $UvExe run --python 3.12 python -m ytgrab
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    return $exitCode
}

# --- Main ---------------------------------------------------------------------

function Main {
    Assert-Windows
    $paths = New-RuntimePaths

    try {
        $uvExe = Get-Uv -UvDir $paths.UvDir
        $sourceDir = Get-YtgrabSource -RequestedVersion $Version -WorkDir $paths.WorkDir
        $ffmpegExe = Get-Ffmpeg -FfmpegDir $paths.FfmpegDir

        $exitCode = Start-Ytgrab -UvExe $uvExe -SourceDir $sourceDir -FfmpegExe $ffmpegExe -Paths $paths

        if ($exitCode -ne 0) {
            Write-Warning "ytgrab exited with code $exitCode. Check the log in %LOCALAPPDATA%\ytgrab\logs."
        }
    }
    finally {
        Write-Step "Cleaning up this run's temporary files"
        Remove-Item $paths.WorkDir -Recurse -Force -ErrorAction SilentlyContinue

        if ($FullCleanup) {
            Write-Step "Removing the reusable runtime cache (-FullCleanup was set)"
            Remove-Item $paths.RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
        else {
            Write-Host ""
            Write-Host "Reusable runtime cache kept at $($paths.RuntimeRoot) for faster next launches." -ForegroundColor DarkGray
            Write-Host "Run this script with -FullCleanup to remove it." -ForegroundColor DarkGray
        }
    }
}

Main
