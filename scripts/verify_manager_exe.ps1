# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
# Resume the frozen EXE gate after a completed build without rebuilding it.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$exe = Join-Path $root 'dist/EvilKeyManager.exe'
$report = Join-Path $root 'build/packaging-check.json'
$releasePath = Join-Path $root 'RELEASE_CURRENT.json'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Build the Manager EXE first.' }
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
if ($release.manager.version -ne '1.1.6') { throw 'Manager release version does not match this EXE build.' }
if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report -Force }
Write-Host 'Running the frozen self-test. Windows may request UAC. USB is not opened.'
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test-report',('"' + $report + '"')) -Wait -PassThru -WindowStyle Hidden
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Frozen EXE self-test did not finish successfully.'
}
$check = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if (-not $check.ok -or -not $check.frozen -or $check.usb_opened -ne $false) {
    throw 'Frozen EXE, USB worker, or no-USB self-test failed.'
}
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$artifact = Join-Path $root 'artifacts/manager/EvilKeyManager.exe'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $artifact) | Out-Null
Copy-Item -LiteralPath $exe -Destination $artifact -Force
if ((Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) {
    throw 'Copied Manager artifact differs from the tested EXE.'
}
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText(($exe + '.sha256'),($hash + '  EvilKeyManager.exe' + "`n"),$utf8)
[IO.File]::WriteAllText(($artifact + '.sha256'),($hash + '  EvilKeyManager.exe' + "`n"),$utf8)
$release.manager.artifact = 'artifacts/manager/EvilKeyManager.exe'
$release.manager.sha256 = $hash
$release.manager.frozen_self_test = 'ok; USB not opened'
[void]$release.PSObject.Properties.Remove('manager_candidate')
$release.publication_status = 'built and locally verified; physical device test separate'
[IO.File]::WriteAllText($releasePath,(($release | ConvertTo-Json -Depth 12) + "`n"),$utf8)
Write-Host ('VERIFIED: ' + $artifact) -ForegroundColor Green
Write-Host ('SHA-256: ' + $hash)
