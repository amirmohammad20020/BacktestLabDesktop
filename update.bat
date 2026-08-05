@echo off
chcp 65001 > nul
title BacktestLab Git Update

echo ===========================
echo   BacktestLab Git Update
echo ===========================
echo.

set /p message=Update title: 

echo.
echo Adding files...
git add .

echo.
echo Creating commit...
git commit -m "%message%"

echo.
echo Uploading to GitHub...
git push

echo.
echo Update finished
pause