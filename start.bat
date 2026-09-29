@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%backend\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Backend environment is missing.
  echo Run: python -m venv backend\.venv
  echo Run: backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
  exit /b 1
)

if not exist "%PROJECT_DIR%frontend\node_modules" (
  echo Frontend dependencies are missing.
  echo Run: npm.cmd --prefix frontend install
  exit /b 1
)

start "RouteFlow API" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\start-api.ps1"
start "RouteFlow UI" /b npm.cmd --prefix "%PROJECT_DIR%frontend" run dev
echo RouteFlow started: API http://127.0.0.1:8000/health, UI http://localhost:5173
endlocal
