@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0anime_taste_analyzer.py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python "%~dp0anime_taste_analyzer.py"
  ) else (
    echo Python was not found.
    echo Install Python from https://www.python.org/downloads/windows/ and enable "Add Python to PATH".
    echo.
    pause
    exit /b 1
  )
)
echo.
pause
