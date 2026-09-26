@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-manager\Scripts\python.exe" (
 echo First run install.cmd. To use an existing Python environment, see README.md.
 pause
 exit /b 1
)
".venv-manager\Scripts\python.exe" "run_manager.py" --demo
if errorlevel 1 pause
