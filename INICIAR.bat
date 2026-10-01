@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set ATIVO=EURUSD-OTC
set /p ATIVO=Ativo (Enter = EURUSD-OTC): 
python -m iqbot saldo
python -m iqbot robo --ativo %ATIVO%
pause
