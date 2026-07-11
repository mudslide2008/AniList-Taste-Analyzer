@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -c "import PIL, playwright" >nul 2>nul
  if errorlevel 1 (
    echo Installing required packages...
    py -m pip install -r requirements.txt
    if errorlevel 1 (
      echo.
      echo Required packages could not be installed.
      pause
      exit /b 1
    )
  )
  py main.py
) else (
  python -c "import PIL, playwright" >nul 2>nul
  if errorlevel 1 (
    echo Installing required packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
      echo.
      echo Required packages could not be installed.
      pause
      exit /b 1
    )
  )
  python main.py
)
pause
