@echo off
cd /d "%~dp0"
echo Bot ishga tushmoqda...
pip install -r requirements.txt -q
python bot.py
pause
