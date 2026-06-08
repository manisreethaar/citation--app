@echo off
echo Starting Auto-Citer + Plagiarism Checker...
echo.
echo   Auto-Citer       : http://localhost:5000
echo   Plagiarism Check : http://localhost:5000/check
echo.
cd /d "D:\NEW APP\v2"
start http://localhost:5000
python app.py
pause
