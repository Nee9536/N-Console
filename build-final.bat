@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================
echo N-Console 22.0.3 - FINAL BUILD
 echo ==============================================


if not exist "assets\n_console_icon.ico" goto :asset_error
if not exist "assets\n_console_icon.png" goto :asset_error
if not exist "assets\home_illustration.png" goto :asset_error

py -m pip install -r requirements.txt || goto :error
py -m pip install pyinstaller pillow || goto :error
py make_ico.py || goto :error

if exist build\N-Console-x64 rmdir /s /q build\N-Console-x64

echo.
echo [1/2] Building x64 application...
py -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "N-Console" ^
  --icon "assets\n_console_icon.ico" ^
  --add-data "assets;assets" ^
  --distpath "build\N-Console-x64" ^
  main.py || goto :error

echo.
echo [2/2] x64 build completed.
echo.
echo Now open Inno Setup and compile:
echo   installer\N-Console-x64.iss

echo.
echo NOTE: x86 requires a 32-bit Python environment.
echo For x86, run PyInstaller with --distpath "build\N-Console-x86"
echo and then compile installer\N-Console-x86.iss

echo.
echo FINAL BUILD READY.
echo Assets bundled: icon + home illustration
pause
exit /b 0

:asset_error
echo.
echo BUILD FAILED: required splash/icon assets are missing.
echo Check assets\n_console_icon.ico, assets\n_console_icon.png and assets\home_illustration.png
pause
exit /b 2

:error
echo.
echo BUILD FAILED. Check the error above.
pause
exit /b 1
