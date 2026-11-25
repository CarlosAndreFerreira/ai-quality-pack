@echo off
setlocal
set "ROOT=%~dp0.."
where python >nul 2>nul
if %errorlevel%==0 (
  python "%ROOT%\skills\long-horizon\scripts\memory.py" %*
  exit /b %errorlevel%
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%ROOT%\skills\long-horizon\scripts\memory.py" %*
  exit /b %errorlevel%
)
echo aqp-memory: no python or py on PATH 1>&2
exit /b 1
