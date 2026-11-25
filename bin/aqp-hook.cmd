@echo off
setlocal
set "ROOT=%~dp0.."
where python >nul 2>nul
if %errorlevel%==0 (
  python "%ROOT%\hooks\aqp_hook.py" %*
  exit /b %errorlevel%
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%ROOT%\hooks\aqp_hook.py" %*
  exit /b %errorlevel%
)
echo aqp-hook: no python or py on PATH 1>&2
exit /b 1
