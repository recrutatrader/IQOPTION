@echo off
chcp 65001 >nul
echo === Preparando o agente da IQ Option ===
where claude >nul 2>nul
if errorlevel 1 (
  echo Instalando o Claude Code...
  curl -fsSL https://claude.ai/install.cmd -o "%TEMP%\install.cmd" && call "%TEMP%\install.cmd" && del "%TEMP%\install.cmd"
) else (
  echo Claude Code ja esta instalado.
)
echo.
echo Abrindo a pagina da extensao Claude in Chrome...
start "" "https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn"
echo.
echo 1. No Chrome, clique em "Usar no Chrome" e entre com a mesma conta do Claude.
echo 2. Feche esta janela e de dois cliques em AGENTE.bat
pause
