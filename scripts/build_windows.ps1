# SPDX-License-Identifier: LicenseRef-EvilKey-Manager-1.0
[CmdletBinding()]
param(
    [switch]$Folder,
    [string]$PythonExe,
    [switch]$CheckPython
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'build') | Out-Null
$Transcript = Join-Path $Root 'build\build-windows.log'
Start-Transcript -LiteralPath $Transcript -Force | Out-Null
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    $ProbeFile = Join-Path $Root 'packaging\python_probe.py'
    $ProbeLog = Join-Path $Root 'build\python-detection.log'
    if (-not (Test-Path -LiteralPath $ProbeFile -PathType Leaf)) {
        throw 'Missing packaging\python_probe.py. Extract the complete package.'
    }
    Set-Content -LiteralPath $ProbeLog -Value ('Python detection R1; PowerShell ' + $PSVersionTable.PSVersion) -Encoding UTF8
    Write-Host ('PowerShell: ' + $PSVersionTable.PSVersion)

    function Test-BuildPython {
        param([string]$Executable, [string[]]$PrefixArguments = @())
        $CallArguments = @($PrefixArguments) + @('-I', $ProbeFile)
        $Label = ($Executable + ' ' + ($PrefixArguments -join ' ')).Trim()
        Write-Host ('Checking: ' + $Label)
        Add-Content -LiteralPath $ProbeLog -Value ("`r`n=== " + $Label + ' ===') -Encoding UTF8
        $Output = @()
        $Code = -1
        $SavedErrorPreference = $ErrorActionPreference
        $SavedAutoInstall = [Environment]::GetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'Process')
        $SavedLegacyInstall = [Environment]::GetEnvironmentVariable('PYLAUNCHER_ALLOW_INSTALL', 'Process')
        try {
            [Environment]::SetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'false', 'Process')
            [Environment]::SetEnvironmentVariable('PYLAUNCHER_ALLOW_INSTALL', $null, 'Process')
            # Windows PowerShell 5.1 wraps native stderr as ErrorRecord. Capture it
            # without letting ErrorAction=Stop replace the actual Python error.
            $ErrorActionPreference = 'Continue'
            $Output = @(& $Executable @CallArguments 2>&1)
            $Code = $LASTEXITCODE
        } catch {
            $Output += $_.Exception.Message
        } finally {
            $ErrorActionPreference = $SavedErrorPreference
            [Environment]::SetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', $SavedAutoInstall, 'Process')
            [Environment]::SetEnvironmentVariable('PYLAUNCHER_ALLOW_INSTALL', $SavedLegacyInstall, 'Process')
        }
        $Text = ($Output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        Add-Content -LiteralPath $ProbeLog -Value ('ExitCode: ' + $Code + "`r`n" + $Text) -Encoding UTF8
        $Report = $null
        try {
            $JsonLine = $Output | ForEach-Object { [string]$_ } | Where-Object { $_.TrimStart().StartsWith('{') } | Select-Object -Last 1
            if ($JsonLine) { $Report = $JsonLine | ConvertFrom-Json -ErrorAction Stop }
        } catch {
            Add-Content -LiteralPath $ProbeLog -Value ('JSON parse: ' + $_.Exception.Message) -Encoding UTF8
        }
        if ($Code -eq 0 -and $Report -and $Report.schema -eq 'evilkey-build-python-v1' -and $Report.ok -eq $true -and $Report.executable) {
            if (Test-Path -LiteralPath $Report.executable -PathType Leaf) {
                Write-Host ('  OK: Python ' + $Report.version + '; x64; Tk ' + $Report.tcl_tk.tk) -ForegroundColor Green
                return $Report
            }
        }
        if ($Report -and $Report.errors) {
            Write-Host ('  Skipped: ' + ($Report.errors -join ' '))
        } elseif ($Text) {
            Write-Host ('  Skipped: ' + $Text)
        } else {
            Write-Host ('  Skipped: no probe response; code ' + $Code)
        }
        return $null
    }

    $Chosen = $null
    if ($PythonExe) {
        $Chosen = Test-BuildPython -Executable $PythonExe
        if (-not $Chosen) { throw ('The selected Python failed the probe. Details: ' + $ProbeLog) }
    } else {
        # Reuse a valid build environment first, without deleting broken ones.
        $ExistingPython = Join-Path $Root '.venv-exe\Scripts\python.exe'
        if (Test-Path -LiteralPath $ExistingPython -PathType Leaf) {
            $Chosen = Test-BuildPython -Executable $ExistingPython
        }
        if (-not $Chosen -and $env:VIRTUAL_ENV) {
            $ActivePython = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
            if (Test-Path -LiteralPath $ActivePython -PathType Leaf) {
                $Chosen = Test-BuildPython -Executable $ActivePython
            }
        }
        # Read the launcher's list, then invoke actual paths. Do not request
        # missing runtime versions: newer launchers may offer automatic installs.
        if (-not $Chosen) {
            $Launchers = @(Get-Command py.exe -All -CommandType Application -ErrorAction SilentlyContinue)
            foreach ($Launcher in $Launchers) {
                $SavedErrorPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = 'Continue'
                    $Listing = @(& $Launcher.Source --list-paths 2>&1)
                    $ListCode = $LASTEXITCODE
                } catch {
                    $Listing = @($_.Exception.Message)
                    $ListCode = -1
                } finally {
                    $ErrorActionPreference = $SavedErrorPreference
                }
                Add-Content -LiteralPath $ProbeLog -Value ("`r`n=== " + $Launcher.Source + ' --list-paths; code=' + $ListCode + " ===`r`n" + ($Listing -join "`r`n")) -Encoding UTF8
                if ($ListCode -eq 0) {
                    foreach ($Line in $Listing) {
                        # Supported launchers return a version tag and a full EXE path.
                        if ([string]$Line -match '(?i)((?:[a-z]:\\|\\\\)[^\r\n]*?python(?:[0-9.]*)?\.exe)"?\s*$') {
                            $Chosen = Test-BuildPython -Executable $Matches[1]
                            if ($Chosen) { break }
                        }
                    }
                }
                if ($Chosen) { break }
            }
        }
        if (-not $Chosen) {
            $PythonCommands = @(Get-Command python.exe, python3.exe -All -CommandType Application -ErrorAction SilentlyContinue)
            foreach ($PythonCommand in $PythonCommands) {
                $Chosen = Test-BuildPython -Executable $PythonCommand.Source
                if ($Chosen) { break }
            }
        }
        # Standard CPython registrations also work without PATH/Python Launcher.
        if (-not $Chosen) {
            foreach ($RegistryPath in @('HKCU:\Software\Python\PythonCore\*\InstallPath', 'HKLM:\Software\Python\PythonCore\*\InstallPath')) {
                $Keys = @(Get-Item -Path $RegistryPath -ErrorAction SilentlyContinue)
                foreach ($Key in $Keys) {
                    $RegisteredPython = $Key.GetValue('ExecutablePath')
                    if (-not $RegisteredPython) {
                        $InstallDir = $Key.GetValue('')
                        if ($InstallDir) { $RegisteredPython = Join-Path $InstallDir 'python.exe' }
                    }
                    if ($RegisteredPython -and (Test-Path -LiteralPath $RegisteredPython -PathType Leaf)) {
                        $Chosen = Test-BuildPython -Executable $RegisteredPython
                        if ($Chosen) { break }
                    }
                }
                if ($Chosen) { break }
            }
        }
    }
    if (-not $Chosen) {
        throw ('No detected Python passed the probe. Inspect build\python-detection.log or pass -PythonExe with the full path to python.exe.')
    }
    $BasePython = [string]$Chosen.executable
    Write-Host ('Selected Python: ' + $BasePython)
    if ($CheckPython) {
        Write-Host 'PYTHON_OK. Interpreter and Tcl/Tk checked. No packages installed, EXE built, or USB opened.' -ForegroundColor Green
        return
    }
    $Venv = Join-Path $Root '.venv-exe'
    $Python = Join-Path $Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Venv)) {
        Write-Host 'Creating an isolated build environment...'
        & $BasePython -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'The .venv-exe interpreter is missing. This script does not delete environments automatically.' }
    if ((Get-Item -LiteralPath $Python).Length -eq 0) { throw 'The .venv-exe interpreter is empty. Check Windows protection logs; do not disable protection.' }
    $VenvReport = Test-BuildPython -Executable $Python
    if (-not $VenvReport) { throw 'The .venv-exe environment does not meet requirements. Preserve it under another name before rebuilding.' }
    Write-Host 'Python and Tk detection passed the build probe.'
    Write-Host 'Installing dependencies...'
    & $Python -m pip install --disable-pip-version-check -r (Join-Path $Root 'packaging\requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install dependencies. Check the connection and pip output.' }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are inconsistent.' }
    & $Python (Join-Path $Root 'packaging\collect_licenses.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not collect license information.' }
    Write-Host 'Logic and GUI tests (without device access)...'
    & $Python -m unittest discover -s tests -p 'test_manager.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Logic tests failed.' }
    & $Python -m unittest tests.test_loot -v
    if ($LASTEXITCODE -ne 0) { throw 'loot.bin/loot.idx decoder tests failed.' }
    & $Python (Join-Path $Root 'scripts\run_tests.py') --gui-only
    if ($LASTEXITCODE -ne 0) { throw 'GUI tests failed.' }
    Write-Host 'Building the USB module...'
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Root 'build\worker') --workpath (Join-Path $Root 'build\pyi-worker') (Join-Path $Root 'packaging\usb_worker.spec')
    if ($LASTEXITCODE -ne 0) { throw 'USB module build failed.' }
    $env:EVILKEY_ONE_FOLDER = if ($Folder) { '1' } else { '0' }
    Write-Host 'Building the portable application...'
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Root 'dist') --workpath (Join-Path $Root 'build\pyi-gui') (Join-Path $Root 'packaging\manager.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    $Exe = if ($Folder) { Join-Path $Root 'dist\EvilKeyManager\EvilKeyManager.exe' } else { Join-Path $Root 'dist\EvilKeyManager.exe' }
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'Output EXE was not found.' }
    $Bytes = [IO.File]::ReadAllBytes($Exe)
    if ($Bytes.Length -lt 100000 -or $Bytes[0] -ne 0x4D -or $Bytes[1] -ne 0x5A) { throw 'Invalid executable file.' }
    $Bytes = $null
    Write-Host 'Checking the frozen EXE. Windows may ask for UAC approval. This test does not open USB.'
    $Report = Join-Path $Root 'build\packaging-check.json'
    if (Test-Path -LiteralPath $Report) { Remove-Item -LiteralPath $Report }
    $Process = Start-Process -FilePath $Exe -ArgumentList @('--self-test-report',('"' + $Report + '"')) -Wait -PassThru -WindowStyle Hidden
    if ($Process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Report)) { throw 'EXE was built, but its self-test failed. Check build\packaging-check.json.' }
    $Check = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    if (-not $Check.ok) { throw 'Application or bundled USB module self-test failed.' }
    $Hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLower()
    [IO.File]::WriteAllText(($Exe + '.sha256'), $Hash + '  EvilKeyManager.exe' + [Environment]::NewLine)
    if (-not $Folder) {
        $ReleasePath = Join-Path $Root 'RELEASE_CURRENT.json'
        $ReleaseInfo = Get-Content -LiteralPath $ReleasePath -Raw | ConvertFrom-Json
        if ($ReleaseInfo.manager.version -ne '1.1.6') { throw 'Manager version in RELEASE_CURRENT.json does not match this build.' }
        $Artifact = Join-Path $Root 'artifacts\manager\EvilKeyManager.exe'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Artifact) | Out-Null
        Copy-Item -LiteralPath $Exe -Destination $Artifact -Force
        if ((Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLower() -ne $Hash) { throw 'Manager artifact hash differs from the tested EXE.' }
        [IO.File]::WriteAllText(($Artifact + '.sha256'), $Hash + '  EvilKeyManager.exe' + [Environment]::NewLine)
        $ReleaseInfo.manager.artifact = 'artifacts/manager/EvilKeyManager.exe'
        $ReleaseInfo.manager.sha256 = $Hash
        $ReleaseInfo.manager.frozen_self_test = 'ok; USB not opened'
        [IO.File]::WriteAllText($ReleasePath, (($ReleaseInfo | ConvertTo-Json -Depth 12) + "`n"), (New-Object Text.UTF8Encoding($false)))
    }
    & $Python -m pip freeze | Set-Content -LiteralPath (Join-Path $Root 'build\dependencies-resolved.txt') -Encoding UTF8
    Write-Host "`nREADY: $Exe" -ForegroundColor Green
    if (-not $Folder) { Write-Host ('Release artifact: ' + $Artifact) }
    if ($Folder) { Write-Host 'Move the complete dist\EvilKeyManager directory and preserve file permissions.' }
    else { Write-Host 'Only EvilKeyManager.exe is needed to run. Keep source code separately.' }
    Write-Host 'Run the physical device test separately.'
} catch {
    Write-Host ("`nSTOPPED: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ("Log: " + $Transcript)
    exit 1
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
}
