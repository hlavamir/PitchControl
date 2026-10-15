@echo off
rem Build PitchControl into dist\PitchControl\ (run on Windows).
rem
rem Everything the steps print goes to build-windows.log; the window shows the step
rem names and, if a step fails, the end of the log. The window stays open at the end (not on CI,
rem where the GitHub workflow sets CI and wants the output on the console).
rem
rem What is installed (the UI packages, the Python environment) is checked first and only installed when it is missing
rem or out of date: the script says what and why and asks once ("Install now? [Y/n]", Enter = yes). On CI it installs
rem without asking. "--check" only says what would be installed.
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%ROOT%\build-windows.log"
set "OUT=>> "%LOG%" 2>&1"
if defined CI set "OUT="
set "RC=0"
> "%LOG%" echo PitchControl Windows build, %DATE% %TIME%
>> "%LOG%" echo Folder: %ROOT%

set "STEP=checking the tools"
echo == %STEP%
>> "%LOG%" echo == %STEP%
where node >NUL 2>&1 || (echo Node.js was not found. Install the LTS version from https://nodejs.org and run this again.& goto :fail)
rem the UI build (Vite 8) needs Node 20.19 or newer, or 22.12 or newer
for /f "tokens=1,2 delims=v." %%a in ('node --version') do (set "NODE_MAJOR=%%a" & set "NODE_MINOR=%%b")
set "NODE_OK="
if %NODE_MAJOR% GTR 22 set "NODE_OK=1"
if %NODE_MAJOR% EQU 22 if %NODE_MINOR% GEQ 12 set "NODE_OK=1"
if %NODE_MAJOR% EQU 20 if %NODE_MINOR% GEQ 19 set "NODE_OK=1"
if not defined NODE_OK (echo Node.js %NODE_MAJOR%.%NODE_MINOR% is too old: the UI build needs 20.19 or newer, or 22.12 or newer. Install the LTS version from https://nodejs.org and run this again.& goto :fail)
for /f %%v in ('node --version') do set "NODE_VER=%%v"
rem python-rtmidi publishes Windows wheels only up to Python 3.12 (newer versions would need a C++ compiler),
rem so the environment is made with 3.12 or 3.11, even when a newer Python is installed next to it
set "PYLAUNCH="
where py >NUL 2>&1
if not errorlevel 1 (
    py -3.12 --version >NUL 2>&1 && set "PYLAUNCH=py -3.12"
    if not defined PYLAUNCH py -3.11 --version >NUL 2>&1 && set "PYLAUNCH=py -3.11"
)
if not defined PYLAUNCH python -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >NUL 2>&1 && set "PYLAUNCH=python"
where uv >NUL 2>&1 && set "HAVE_UV=1"
if not defined PYLAUNCH if not defined HAVE_UV (echo Python 3.12 or 3.11 was not found. Install Python 3.12 from https://www.python.org - it can stay next to a newer Python - and run this again.& goto :fail)
(
    echo node:& node --version
    echo npm:& call npm --version
    echo python:& python --version
    echo py -0p:& py -0p
    echo Python used: %PYLAUNCH%
    echo uv:& uv --version
    echo git:& git --version
) >> "%LOG%" 2>&1

set "STEP=checking what needs installing"
echo == %STEP%
>> "%LOG%" echo == %STEP%
rem A marker file inside each environment says what it was installed with: the Node or Python version and the hash of the
rem file that lists the packages. Missing or different: it is installed again. node_modules is only valid for the Node
rem version that installed it: with an older Node, npm skips the platform binary of the build tool (Rolldown), and it is
rem not added when Node is upgraded later.
set "LOCK_HASH="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "%ROOT%\frontend\package-lock.json" SHA256') do if not defined LOCK_HASH set "LOCK_HASH=%%h"
set "LOCK_HASH=%LOCK_HASH: =%"
set "PYPROJECT_HASH="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "%ROOT%\backend\pyproject.toml" SHA256') do if not defined PYPROJECT_HASH set "PYPROJECT_HASH=%%h"
set "PYPROJECT_HASH=%PYPROJECT_HASH: =%"
set "UI_NOW=%NODE_VER% %LOCK_HASH%"
rem Flat lines, not blocks: a variable set inside a (...) block is expanded before the block runs.
set "NEED_UI="
set "UI_THEN="
set "THEN_NODE="
if not exist frontend\node_modules set "NEED_UI=not installed yet"
if not defined NEED_UI if not exist frontend\node_modules\.installed-with set "NEED_UI=no record of what installed them yet"
if not defined NEED_UI set /p UI_THEN=<frontend\node_modules\.installed-with
if not defined NEED_UI for /f "tokens=1" %%a in ("%UI_THEN%") do set "THEN_NODE=%%a"
if not defined NEED_UI if not "%THEN_NODE%"=="%NODE_VER%" set "NEED_UI=installed with Node %THEN_NODE%, now Node %NODE_VER%"
if not defined NEED_UI if not "%UI_THEN%"=="%UI_NOW%" set "NEED_UI=package-lock.json changed since the last install"
set "NEED_PY="
set "REMOVE_VENV="
set "PY_VER="
set "PY_THEN="
if not exist backend\.venv\Scripts\python.exe set "NEED_PY=not created yet"
rem an environment from an unsuitable Python (an earlier try) is thrown away
if not defined NEED_PY backend\.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >NUL 2>&1 || (set "NEED_PY=made with a Python that is not 3.11 or 3.12" & set "REMOVE_VENV=1")
if not defined NEED_PY for /f "delims=" %%v in ('backend\.venv\Scripts\python.exe --version') do set "PY_VER=%%v"
if not defined NEED_PY if not exist backend\.venv\.installed-with set "NEED_PY=no record of what installed it yet"
if not defined NEED_PY set /p PY_THEN=<backend\.venv\.installed-with
if not defined NEED_PY if not "%PY_THEN%"=="%PY_VER% %PYPROJECT_HASH%" set "NEED_PY=pyproject.toml or the Python version changed since the last install"
if not defined NEED_UI if not defined NEED_PY goto :nothing_to_install
echo Needs installing:
>> "%LOG%" echo Needs installing:
if defined NEED_UI echo   UI packages (npm ci): %NEED_UI%
if defined NEED_UI >> "%LOG%" echo   UI packages: %NEED_UI%
if defined NEED_PY echo   Python environment (pip install): %NEED_PY%
if defined NEED_PY >> "%LOG%" echo   Python environment: %NEED_PY%
if /i "%~1"=="--check" goto :end
if defined CI goto :checked
set "ANSWER=y"
set /p "ANSWER=Install now? [Y/n] "
if /i "%ANSWER:~0,1%"=="n" goto :declined
goto :checked
:nothing_to_install
if /i "%~1"=="--check" echo Nothing to install.
if /i "%~1"=="--check" goto :end
:checked

set "STEP=web UI"
echo == %STEP%
>> "%LOG%" echo == %STEP%
pushd frontend
if defined NEED_UI (
    echo installing the UI packages
    if exist node_modules rmdir /s /q node_modules
    call npm ci --silent %OUT% || goto :fail
    > node_modules\.installed-with echo %UI_NOW%
)
call npm run build --silent %OUT% || goto :fail
popd

set "STEP=Python environment"
echo == %STEP%
>> "%LOG%" echo == %STEP%
pushd backend
if defined REMOVE_VENV rmdir /s /q .venv >NUL 2>&1
if defined NEED_PY (
    echo installing the Python environment
    if defined HAVE_UV (
        if not exist .venv\Scripts\python.exe uv venv -q --python 3.12 .venv %OUT% || goto :fail
        uv pip install -q --python .venv\Scripts\python.exe -e ".[build]" %OUT% || goto :fail
    ) else (
        if not exist .venv\Scripts\python.exe %PYLAUNCH% -m venv .venv %OUT% || goto :fail
        .venv\Scripts\python.exe -m pip install -q -e ".[build]" %OUT% || goto :fail
    )
)
rem the marker is written outside the block above: %PY_VER% would be expanded before it is set
if defined NEED_PY for /f "delims=" %%v in ('.venv\Scripts\python.exe --version') do set "PY_VER=%%v"
if defined NEED_PY > .venv\.installed-with echo %PY_VER% %PYPROJECT_HASH%
popd
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist packaging\icon.ico "%PY%" packaging\make_icon.py %OUT%

set "STEP=PyInstaller"
echo == %STEP%
>> "%LOG%" echo == %STEP%
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build packaging\pitchcontrol.spec %OUT% || goto :fail

set "STEP=smoke test"
echo == %STEP%
>> "%LOG%" echo == %STEP%
dist\PitchControl\PitchControl.exe --smoke-test --no-hardware --data "%TEMP%\pitchcontrol-smoke" --port 8499 %OUT% || goto :fail

set "STEP=zip"
echo == %STEP%
>> "%LOG%" echo == %STEP%
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\PitchControl -DestinationPath dist\PitchControl-windows-x64.zip" %OUT% || goto :fail
echo Done: dist\PitchControl\PitchControl.exe and dist\PitchControl-windows-x64.zip
>> "%LOG%" echo Done.
goto :end

:declined
echo Not installed. To do it by hand:
if defined NEED_UI echo   cd frontend ^&^& npm ci
if defined NEED_PY echo   cd backend ^&^& py -3.12 -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -e ".[build]"
set "RC=1"
goto :end

:fail
set "RC=1"
echo.
echo BUILD FAILED in step: %STEP%
>> "%LOG%" echo BUILD FAILED in step: %STEP%
if defined OUT (
    echo Last lines of the log:
    powershell -NoProfile -Command "Get-Content -Tail 30 -LiteralPath $env:LOG"
)
echo Full log: %LOG%

:end
if not defined CI (
    echo.
    echo Press any key to close this window.
    pause >NUL
)
exit /b %RC%
