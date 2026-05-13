@echo off
:: Cria uma tarefa agendada no Windows para rodar o dashboard todo dia às 07:30
:: Execute este arquivo como ADMINISTRADOR

set SCRIPT_DIR=%~dp0
set PYTHON_CMD=python
set SCRIPT_PATH=%SCRIPT_DIR%dashboard_mercado.py

echo Configurando tarefa agendada...
echo Diretorio: %SCRIPT_DIR%
echo Script:    %SCRIPT_PATH%
echo Horario:   07:30 todos os dias uteis

schtasks /create /tn "Dashboard Financeiro Matinal" ^
  /tr "\"%PYTHON_CMD%\" \"%SCRIPT_PATH%\"" ^
  /sc WEEKDAYS ^
  /st 07:30 ^
  /ru %USERNAME% ^
  /f

if %ERRORLEVEL%==0 (
  echo.
  echo [OK] Tarefa agendada com sucesso!
  echo      Sera executada todo dia util as 07:30
  echo.
  echo Para verificar: schtasks /query /tn "Dashboard Financeiro Matinal"
  echo Para remover:   schtasks /delete /tn "Dashboard Financeiro Matinal" /f
) else (
  echo.
  echo [ERRO] Falha ao criar tarefa. Execute este .bat como Administrador.
)
pause
