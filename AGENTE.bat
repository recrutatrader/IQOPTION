@echo off
chcp 65001 >nul
cd /d "%~dp0"
where claude >nul 2>nul
if errorlevel 1 (
  echo Claude Code nao encontrado. Rode o INSTALAR.bat e depois abra este arquivo de novo.
  pause
  exit /b
)
claude --chrome "Comece: abra a IQ Option no meu Chrome e me diga o que esta na tela."
