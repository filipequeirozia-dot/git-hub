@echo off
echo Instalando dependencias do Dashboard Financeiro...
echo.
pip install anthropic requests beautifulsoup4 lxml python-dotenv
echo.
if %ERRORLEVEL%==0 (
  echo [OK] Dependencias instaladas!
  echo.
  echo Proximo passo:
  echo   1. Copie .env.example para .env
  echo   2. Preencha ANTHROPIC_API_KEY=sua-chave
  echo   3. Execute: python dashboard_mercado.py
) else (
  echo [ERRO] Falha na instalacao. Verifique se Python esta no PATH.
)
pause
