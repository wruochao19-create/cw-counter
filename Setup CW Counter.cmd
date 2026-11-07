@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" setup_windows.py
  goto done
)
if defined CW_PYTHON (
  "%CW_PYTHON%" setup_windows.py
  goto done
)
py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>&1
if not errorlevel 1 (
  py -3.12 setup_windows.py
  goto done
)
python -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>&1
if not errorlevel 1 (
  python setup_windows.py
  goto done
)
echo Install Python 3.12 x64 with Tcl/Tk from https://www.python.org/downloads/windows/
echo Then run this file again. An agent can also set CW_PYTHON to python.exe.
pause
exit /b 1
:done
if errorlevel 1 (
  echo Setup failed. Read the error above or README.md.
  pause
  exit /b 1
)
echo Ready. You can close this window and start CW Counter.
pause
