@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 가상 데이터로 연습하는 모드입니다. 실제 데이터와 완전히 분리된 "테스트데이터" 폴더를 사용합니다.
set GOUN_DATA_DIR=%~dp0테스트데이터
".venv\Scripts\python.exe" -m tests.seed_demo "%GOUN_DATA_DIR%"
start "" ".venv\Scripts\pythonw.exe" -m app
