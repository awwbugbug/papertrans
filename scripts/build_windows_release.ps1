param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repository ".venv\Scripts\python.exe"
$frontend = Join-Path $repository "frontend"
$tauriRoot = Join-Path $frontend "src-tauri"
$releaseRoot = Join-Path $repository "build\windows-release"
$sidecarWork = Join-Path $releaseRoot "pyinstaller"
$sidecarDist = Join-Path $releaseRoot "sidecar"
$binaryRoot = Join-Path $tauriRoot "binaries"
$targetBinary = Join-Path $binaryRoot "papertrans-backend-x86_64-pc-windows-msvc.exe"
$entryPoint = Join-Path $repository "scripts\papertrans_sidecar.py"
$ocrModelRoot = Join-Path $repository "models\paddleocr"
$ocrModelDirectories = @(
    (Join-Path $ocrModelRoot "PP-OCRv6_medium_det_infer"),
    (Join-Path $ocrModelRoot "PP-OCRv6_medium_rec_infer")
)

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment not found: $python"
}

foreach ($modelDirectory in $ocrModelDirectories) {
    if (-not (Test-Path -LiteralPath $modelDirectory -PathType Container)) {
        throw "Required bundled OCR model directory not found: $modelDirectory"
    }
    foreach ($modelFile in @("inference.json", "inference.pdiparams", "inference.yml")) {
        $matches = @(Get-ChildItem -LiteralPath $modelDirectory -Filter $modelFile -File -Recurse)
        if ($matches.Count -ne 1) {
            throw "Expected exactly one $modelFile under bundled OCR model: $modelDirectory"
        }
    }
}

if (-not $SkipTests) {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Python tests failed" }
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
    Push-Location $frontend
    try {
        corepack pnpm test:ui
        if ($LASTEXITCODE -ne 0) { throw "UI contract tests failed" }
        corepack pnpm test:sites
        if ($LASTEXITCODE -ne 0) { throw "Sites tests failed" }
    }
    finally {
        Pop-Location
    }
}

& $python (Join-Path $repository "scripts\build_icon_assets.py")
if ($LASTEXITCODE -ne 0) { throw "PaperTrans icon generation failed" }
Push-Location $frontend
try {
    corepack pnpm tauri icon "..\assets\branding\papertrans-icon.png" --output "src-tauri\icons"
    if ($LASTEXITCODE -ne 0) { throw "Tauri icon generation failed" }
}
finally {
    Pop-Location
}

foreach ($managedPath in @($releaseRoot, $binaryRoot)) {
    $fullManagedPath = [System.IO.Path]::GetFullPath($managedPath)
    $repositoryPrefix = $repository.TrimEnd('\') + '\'
    if (-not $fullManagedPath.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to manage path outside the repository: $fullManagedPath"
    }
}

if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $sidecarWork, $sidecarDist, $binaryRoot -Force | Out-Null
if (Test-Path -LiteralPath $targetBinary) {
    Remove-Item -LiteralPath $targetBinary -Force
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name papertrans-backend `
    --paths (Join-Path $repository "src") `
    --workpath $sidecarWork `
    --specpath $releaseRoot `
    --distpath $sidecarDist `
    --collect-all paddle `
    --collect-all paddleocr `
    $entryPoint
if ($LASTEXITCODE -ne 0) { throw "Python sidecar build failed" }

$builtSidecar = Join-Path $sidecarDist "papertrans-backend.exe"
$smokeData = Join-Path $releaseRoot "smoke-data"
New-Item -ItemType Directory -Path $smokeData -Force | Out-Null
$portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$portProbe.Start()
$smokePort = ([System.Net.IPEndPoint]$portProbe.LocalEndpoint).Port
$portProbe.Stop()
$smokeToken = "papertrans-release-smoke"
$smokeProcess = Start-Process `
    -FilePath $builtSidecar `
    -ArgumentList @("--port", $smokePort, "--token", $smokeToken, "--data-root", $smokeData) `
    -WindowStyle Hidden `
    -PassThru
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $systemInfo = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$smokePort/api/system" `
                -Headers @{ "X-PaperTrans-Token" = $smokeToken } `
                -TimeoutSec 2
            break
        }
        catch {
            if ([DateTime]::UtcNow -ge $deadline) { throw }
        }
    } while ($true)
    if (-not ($systemInfo.providers | Where-Object { $_.name -eq "mock" })) {
        throw "Sidecar smoke test returned an invalid system contract"
    }
}
finally {
    Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and
        [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
            [System.IO.Path]::GetFullPath($builtSidecar),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Copy-Item -LiteralPath $builtSidecar -Destination $targetBinary

Push-Location $frontend
try {
    corepack pnpm desktop:build
    if ($LASTEXITCODE -ne 0) { throw "Tauri installer build failed" }
}
finally {
    Pop-Location
}

$installerRoot = Join-Path $tauriRoot "target\release\bundle\nsis"
$tauriConfig = Get-Content -LiteralPath (Join-Path $tauriRoot "tauri.conf.json") -Raw |
    ConvertFrom-Json
$installerName = "PaperTrans_$($tauriConfig.version)_x64-setup.exe"
$installer = Join-Path $installerRoot $installerName
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "No NSIS installer was produced"
}

$installerItem = Get-Item -LiteralPath $installer
$hash = Get-FileHash -LiteralPath $installerItem.FullName -Algorithm SHA256
$checksum = "$($hash.Hash)  $($installerItem.Name)"
[System.IO.File]::WriteAllText(
    (Join-Path $installerRoot "SHA256SUMS.txt"),
    "$checksum`r`n",
    [System.Text.UTF8Encoding]::new($false)
)
[PSCustomObject]@{
    Installer = $installerItem.FullName
    SizeMiB = [math]::Round($installerItem.Length / 1MB, 1)
    SHA256 = $hash.Hash
} | Format-List
