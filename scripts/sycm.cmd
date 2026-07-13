@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..") do set "SKILL_DIR=%%~fI"

rem Keep Python, dependency caches and the authenticated browser profile inside
rem the project. This works in workspace-only Codex/AI sandboxes that deny AppData.
set "UV_PYTHON_INSTALL_DIR=%SKILL_DIR%\.uv-python"
set "UV_CACHE_DIR=%SKILL_DIR%\.uv-cache"
set "UV_PROJECT_ENVIRONMENT=%SKILL_DIR%\.venv"
set "SYCM_STATE_DIR=%SKILL_DIR%\.runtime"
set "PYTHON_PACKAGES=%SKILL_DIR%\.python-packages"
set "PYTHONPATH=%PYTHON_PACKAGES%;%PYTHONPATH%"

where uv >nul 2>nul
if %errorlevel% equ 0 (
  uv run --with browser-cookie3 --with curl-cffi --with websocket-client python "%SKILL_DIR%\sycm_cli.py" %*
  exit /b !errorlevel!
)

where py >nul 2>nul
if %errorlevel% neq 0 (
  echo Python 3 or uv was not found. Install Python from https://www.python.org/downloads/ 1>&2
  exit /b 1
)

py -3 -c "import browser_cookie3, curl_cffi, websocket" >nul 2>nul
if %errorlevel% neq 0 (
  echo Installing sycm-cli dependencies inside the project... 1>&2
  if not exist "%PYTHON_PACKAGES%" mkdir "%PYTHON_PACKAGES%"
  py -3 -m pip install --target "%PYTHON_PACKAGES%" -r "%SKILL_DIR%\requirements.txt"
  if !errorlevel! neq 0 exit /b !errorlevel!
)

py -3 "%SKILL_DIR%\sycm_cli.py" %*
exit /b %errorlevel%
