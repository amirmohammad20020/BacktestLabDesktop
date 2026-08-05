@echo off
title BacktestLab Git Update

echo ===========================
echo   BacktestLab Git Update
echo ===========================
echo.

set /p message=عنوان آپديت را وارد کن: 

echo.
echo در حال آماده سازي تغييرات...
git add .

echo.
echo در حال ساخت Commit...
git commit -m "%message%"

echo.
echo در حال ارسال به GitHub...
git push

echo.
echo ===========================
echo آپديت تمام شد
echo ===========================

pause