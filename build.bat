@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo N-Console x64 Build
 echo ==========================================
py -m pip install -r requirements.txt
py -m pip install pyinstaller pillow
py make_ico.py
if exist build\N-Console-x64 rmdir /s /q build\N-Console-x64
py -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "N-Console" ^
  --icon "assets\n_console_icon.ico" ^
  --add-data "assets;assets" ^
  --distpath "build\N-Console-x64" ^
  main.py

echo.
echo Build complete.
echo Compile installer\N-Console-x64.iss using Inno Setup 6.
echo Desktop shortcut and Start Menu entry are configured in the ISS file.
pause
