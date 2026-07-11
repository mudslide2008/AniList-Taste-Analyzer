@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -c "import PIL" >nul 2>nul
  if errorlevel 1 (
    echo Installing required image package Pillow...
    py -m pip install Pillow
    if errorlevel 1 (
      echo.
      echo Pillow could not be installed. Try: py -m pip install Pillow
      pause
      exit /b 1
    )
  )
  py main.py
) else (
  python -c "import PIL" >nul 2>nul
  if errorlevel 1 (
    echo Installing required image package Pillow...
    python -m pip install Pillow
    if errorlevel 1 (
      echo.
      echo Pillow could not be installed. Try: python -m pip install Pillow
      pause
      exit /b 1
    )
  )
  python main.py
)
pause
