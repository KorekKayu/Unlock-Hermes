@echo off
rem === IKONA-ONI ===
rem unlock.bat - dobel klik, selesai.
rem
rem   unlock.bat              pasang semuanya (SOUL + HACKMODE + patch + config + watchdog)
rem   unlock.bat --status     cek status patch + HACKMODE
rem   unlock.bat --restore    balikin source asli
rem
rem Argumen apa pun diteruskan ke unlock.py / hermes_unlock.py.
rem Override interpreter: set PYTHON=C:\path\python.exe

setlocal
set "HERE=%~dp0"
set "SPY="

if defined PYTHON if exist "%PYTHON%" set "SPY=%PYTHON%"

rem --- 1) interpreter venv milik Hermes (punya semua dependency) -------------
if not defined SPY if defined HERMES_HOME (
  for /d %%D in ("%HERMES_HOME%\installs\*") do (
    if not defined SPY for /d %%E in ("%%D\environments\*") do (
      if not defined SPY if exist "%%E\venv\Scripts\python.exe" set "SPY=%%E\venv\Scripts\python.exe"
    )
  )
)
if not defined SPY if exist "%LOCALAPPDATA%\hermes\installs" (
  for /d %%D in ("%LOCALAPPDATA%\hermes\installs\*") do (
    if not defined SPY for /d %%E in ("%%D\environments\*") do (
      if not defined SPY if exist "%%E\venv\Scripts\python.exe" set "SPY=%%E\venv\Scripts\python.exe"
    )
  )
)

rem --- 2) py launcher, lalu python di PATH ----------------------------------
if not defined SPY (
  py -3 -c "import sys" >nul 2>&1 && set "SPY=py -3"
)
if not defined SPY (
  python -c "import sys" >nul 2>&1 && set "SPY=python"
)
if not defined SPY (
  echo ERROR: python tidak ketemu. Install Python 3.8+ dari python.org,
  echo        atau set PYTHON=C:\path\python.exe
  pause
  exit /b 1
)

echo [*] interpreter: %SPY%

rem tanpa flag = pasang semuanya; --skip-soul tetap didukung (dibuang dari argumen)
set "ARGS=%*"
if /i "%~1"=="--skip-soul" set "ARGS=%ARGS:--skip-soul=%"

%SPY% "%HERE%unlock.py" %ARGS%
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [x] exit=%RC%
  pause
)
exit /b %RC%
