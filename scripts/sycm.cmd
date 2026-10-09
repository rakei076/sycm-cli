@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem sycm-cli launcher for Windows. Usage: scripts\sycm.cmd <command> [args...]
rem NOTE: keep this file ASCII-only with CRLF line endings. cmd.exe reads it as GBK on Chinese Windows.
for %%I in ("%~dp0..") do set "SKILL_DIR=%%~fI"
rem uv installs its Python under the user profile (default), NOT inside this folder: moving the folder must not break it
set "TB_STATE_ROOT=%SKILL_DIR%\.runtime"
set "PYTHON_PACKAGES=%SKILL_DIR%\.python-packages"
set "PYTHONPATH=%SKILL_DIR%;%PYTHON_PACKAGES%;%PYTHONPATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
rem third-party wmi (pulled in by browser-cookie3 on Windows) prints SyntaxWarnings
set "PYTHONWARNINGS=ignore::SyntaxWarning"
cd /d "%SKILL_DIR%"

rem uv is often installed but not yet on PATH in the current terminal: also look in its default folders
where uv >nul 2>nul
if %errorlevel% neq 0 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
  if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" set "PATH=%LOCALAPPDATA%\Programs\uv;%PATH%"
)

set "DEPS=--with browser-cookie3 --with curl-cffi --with websocket-client --with mcp~=2.3 --with openpyxl --with pillow --with jinja2"
where uv >nul 2>nul
if %errorlevel% equ 0 (
  rem first run: download dependencies separately so a network failure gets a clear message
  uv run -q --no-project --offline !DEPS! python -c "" >nul 2>nul
  if !errorlevel! neq 0 (
    echo First run: downloading dependencies, needs internet, about 1 minute ... 1>&2
    uv run -q --no-project !DEPS! python -c ""
    if !errorlevel! neq 0 goto :nonet
  )
  uv run -q --no-project !DEPS! python -m tb sycm %*
  exit /b !errorlevel!
)
where py >nul 2>nul
if %errorlevel% neq 0 (
  echo Neither uv nor Python 3 was found. 1>&2
  echo Easiest fix: run this in PowerShell, then open a NEW terminal window and retry: 1>&2
  echo    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" 1>&2
  echo Or install Python 3.10+ from https://www.python.org/downloads/ 1>&2
  exit /b 1
)
py -3 -c "import browser_cookie3, curl_cffi, websocket, mcp, openpyxl, PIL, jinja2" >nul 2>nul
if %errorlevel% neq 0 (
  echo First run: installing dependencies into .python-packages ... 1>&2
  if not exist "%PYTHON_PACKAGES%" mkdir "%PYTHON_PACKAGES%"
  py -3 -m pip install -q --target "%PYTHON_PACKAGES%" -r "%SKILL_DIR%\requirements.txt"
  if !errorlevel! neq 0 goto :nonet
)
py -3 -m tb sycm %*
exit /b %errorlevel%

:nonet
echo Could not download Python dependencies: this computer cannot reach pypi.org right now. 1>&2
echo If this command was run by an AI assistant such as Codex: its sandbox blocks internet and local ports by default. 1>&2
echo Use MCP instead: run "scripts\<tool>.cmd mcp install" once in your own terminal, fully restart Codex, then let it use the MCP tools. 1>&2
echo Or run the same command once in a terminal you opened yourself. 1>&2
exit /b 1
