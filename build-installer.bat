@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call build-final.bat
if errorlevel 1 exit /b 1

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo.
  echo Inno Setup 6 was not found.
  echo Install Inno Setup 6, then compile installer\N-Console-x64.iss.
  pause
  exit /b 2
)

echo.
echo Compiling N-Console 22.0.1 x64 installer...
"%ISCC%" "installer\N-Console-x64.iss"
if errorlevel 1 goto :error

echo.
echo ==============================================
echo FINAL INSTALLER CREATED
echo installer\N-Console-Setup-x64.exe
echo ==============================================
pause
exit /b 0

:error
echo.
echo Inno Setup compilation failed.
pause
exit /b 1
