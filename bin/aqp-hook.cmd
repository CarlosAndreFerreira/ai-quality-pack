@echo off
setlocal
set "ROOT=%~dp0.."
rem A name on PATH is not sufficient: on Windows, python3 or python can be the Microsoft Store alias.
call python3 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :use_python3
call python -c "import sys" >nul 2>nul
if not errorlevel 1 goto :use_python
call py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :use_py
echo aqp-hook: no python3, python or py on PATH that runs 1>&2
exit /b 1

:use_python3
python3 "%ROOT%\hooks\aqp_hook.py" %*
exit /b %errorlevel%

:use_python
python "%ROOT%\hooks\aqp_hook.py" %*
exit /b %errorlevel%

:use_py
py -3 "%ROOT%\hooks\aqp_hook.py" %*
exit /b %errorlevel%
