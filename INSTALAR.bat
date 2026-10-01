@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalando o robo IQ Option ===

where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instalando pelo winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Feche esta janela e rode o INSTALAR.bat de novo.
  pause
  exit /b
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto erro
python -m playwright install chromium || goto erro

if not exist .env (
  copy .env.example .env >nul
  powershell -Command "(Get-Content .env) -replace 'IQ_HEADLESS=true','IQ_HEADLESS=false' | Set-Content -Encoding UTF8 .env"
)
echo.
echo Pronto! Coloque seu e-mail e senha da IQ Option no arquivo que vai abrir, salve e feche.
notepad .env
echo Depois de salvar, de dois cliques em INICIAR.bat
pause
exit /b

:erro
echo Ocorreu um erro na instalacao. Copie a mensagem acima e mande para o Claude.
pause
