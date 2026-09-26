@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python bootstrap.py) else (py -3 bootstrap.py)
if errorlevel 1 (
 echo Installation failed. Read the error above. No USB operation was performed.
 pause
 exit /b 1
)
pause
