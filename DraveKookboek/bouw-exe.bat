@echo off
title DraveKookboek - EXE bouwen
cd /d "%~dp0"
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo Nieuwe .venv maken met Python 3.13...
  py -3.13 -m venv .venv || goto mislukt
)
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements.txt pyinstaller pillow || goto mislukt
"%VPY%" make_icon.py
"%VPY%" -m PyInstaller --noconfirm --clean --windowed --onedir --name DraveKookboek --icon assets\icon.ico --add-data "assets;assets" --add-data "DraveKookboek-Snelgids.pdf;." --collect-all neuvoice --collect-all onnxruntime --collect-all sounddevice --hidden-import stem --hidden-import drave_update --exclude-module tkinter --exclude-module PyQt6.QtWebEngineCore --exclude-module PyQt6.QtWebEngineWidgets --exclude-module PyQt6.QtQml --exclude-module PyQt6.QtQuick --exclude-module matplotlib --exclude-module PIL dravekookboek.py
if errorlevel 1 goto mislukt
if not exist "dist\DraveKookboek\DraveKookboek.exe" goto mislukt
xcopy /e /i /y assets "dist\DraveKookboek\assets" >nul
copy /y DraveKookboek-Snelgids.pdf "dist\DraveKookboek\" >nul
echo.
echo KLAAR: dist\DraveKookboek\DraveKookboek.exe
exit /b 0
:mislukt
echo MISLUKT - kijk hierboven voor de fout.
exit /b 1
