@echo off
setlocal

REM Launch YouTube subtitle tool on Windows.
REM Assumes Python and dependencies are already installed.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found in PATH. Please install Python 3 and add it to PATH.
  pause
  exit /b 1
)

python "%~dp0youtube_subtitle_tool.py"
if errorlevel 1 (
  echo.
  echo [ERROR] Program exited with an error.
  pause
  exit /b 1
)

endlocal
