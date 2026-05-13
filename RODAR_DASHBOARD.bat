@echo off
chcp 65001 > nul
title Dashboard Financeiro Matinal
cd /d "%~dp0"

echo ============================================================
echo   DASHBOARD FINANCEIRO MATINAL
echo ============================================================
echo.
echo Iniciando coleta de dados e geracao do dashboard...
echo.

python dashboard_mercado.py

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ============================================================
  echo   ERRO: O script falhou. Possiveis causas:
  echo   - Python nao esta instalado ou nao esta no PATH
  echo   - Dependencias nao instaladas (rode instalar_dependencias.bat)
  echo   - Falha de conexao com a internet
  echo ============================================================
  echo.
  pause
  exit /b 1
)

echo.
echo Dashboard aberto no navegador!
echo Esta janela vai fechar em 5 segundos...
timeout /t 5 > nul
