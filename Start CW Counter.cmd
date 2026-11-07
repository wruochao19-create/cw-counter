@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  set "CW_PYTHON=%~dp0.venv\Scripts\python.exe"
  goto run
)
if exist "%CW_PYTHON%" goto run
echo First run Setup CW Counter.cmd. See README.md for Python installation.
pause
exit /b 1
:run
"%CW_PYTHON%" "%~dp0app.py"
if errorlevel 1 pause
