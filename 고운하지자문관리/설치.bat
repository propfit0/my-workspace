@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] 프로그램 실행 환경을 만듭니다...
python -m venv .venv
if errorlevel 1 (
  echo 파이썬(Python 3.12)이 설치되어 있지 않습니다. https://www.python.org 에서 설치 후 다시 실행하세요.
  pause
  exit /b 1
)
echo [2/2] 필요한 구성요소를 설치합니다(인터넷 필요, 처음 한 번만)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo 설치가 끝났습니다. 이제 [실행.bat]을 더블클릭하세요.
pause
