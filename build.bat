@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat

echo === پاکسازی خروجی قبلی ===
rmdir /s /q build dist Output 2>nul

echo === ساخت exe ===
pyinstaller --clean --noconfirm backtestlab.spec || goto :err

echo === ساخت فایل نصبی ===
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss || goto :err

echo.
echo ======== تمام شد ========
start "" "Output"
pause
exit /b 0

:err
echo.
echo !!! خطا در ساخت !!!
pause
