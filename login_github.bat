@echo off
echo ============================================================
echo  Treetime - GitHub Login
echo ============================================================
echo.
echo This will open your browser to authenticate with GitHub.
echo Follow the prompts, then close this window when done.
echo.
"%~dp0gh.exe" auth login --web -h github.com
echo.
if %ERRORLEVEL% EQU 0 (
    echo Login successful! You can now run build_and_release.bat
) else (
    echo Login failed. Please try again.
)
echo.
pause
