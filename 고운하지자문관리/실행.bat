@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  chcp 65001 >nul
  echo 먼저 [설치.bat]을 실행해 주세요.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m app
