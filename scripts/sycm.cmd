@echo off
setlocal
set "SKILL_DIR=%~dp0.."

where uv >nul 2>nul
if %errorlevel% equ 0 (
  uv run --with browser-cookie3 --with curl-cffi --with websocket-client python "%SKILL_DIR%\sycm_cli.py" %*
  exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel% neq 0 (
  echo Python 3 or uv was not found. Install Python from https://www.python.org/downloads/ 1>&2
  exit /b 1
)

py -3 -c "import browser_cookie3, curl_cffi, websocket" >nul 2>nul
if %errorlevel% neq 0 (
  echo Installing sycm-cli dependencies for this user... 1>&2
  py -3 -m pip install --user -r "%SKILL_DIR%\requirements.txt"
  if %errorlevel% neq 0 exit /b %errorlevel%
)

py -3 "%SKILL_DIR%\sycm_cli.py" %*
exit /b %errorlevel%
