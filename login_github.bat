@echo off
echo ============================================================
echo  Treetime - GitHub Login
echo ============================================================
echo.
echo This will open your browser to authenticate with GitHub.
echo Follow the prompts, then come back here and press any key.
echo.
"C:\Users\User\AppData\Local\gh-cli\bin\gh.exe" auth login --web -h github.com
echo.
if %ERRORLEVEL% EQU 0 (
    echo Login successful!
) else (
    echo Login failed. Please try again.
)
echo.
pause
