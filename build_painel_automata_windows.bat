@echo off
setlocal
title Buildar Painel AUTOMATA.exe

cd /d "%~dp0"

echo Procurando Python 3.8...
set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 py -3.8 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3.8"
if not defined PYTHON (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    echo ERRO: Python 3 nao foi encontrado.
    echo Instale Python 3 em https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
echo Usando: %PYTHON%
%PYTHON% --version

echo Verificando o pip...
%PYTHON% -m ensurepip --upgrade
if errorlevel 1 (
    echo ERRO: nao foi possivel habilitar o pip neste Python.
    pause
    exit /b 1
)

echo Instalando versoes compativeis com Windows/I3 antigo...
%PYTHON% -m pip install --user --upgrade "pyinstaller<7" "pywin32<307" "pillow<11"
if errorlevel 1 (
    echo ERRO: nao foi possivel instalar PyInstaller/pywin32/Pillow.
    echo Verifique a mensagem acima e confirme que o Windows tem internet.
    pause
    exit /b 1
)

REM customtkinter e opcional: sem ele o app abre em tk puro, sem modo escuro
REM e com os controles no desenho do ttk. Nao pode ser erro fatal.
REM O resultado importa depois: os --hidden-import abaixo sao montados so
REM se ele estiver de pe. Hidden import de modulo ausente aborta o build.
set CTK_OK=nao
%PYTHON% -m pip install --user --upgrade "customtkinter"
if not errorlevel 1 set CTK_OK=sim
if "%CTK_OK%"=="nao" (
    echo AVISO: nao foi possivel instalar customtkinter.
    echo O painel vai abrir do mesmo jeito, so que sem modo escuro.
)

REM openpyxl e reportlab sao usados so pela aba Relatorios (XLSX e PDF)
%PYTHON% -m pip install --user --upgrade "openpyxl" "reportlab"
if errorlevel 1 (
    echo AVISO: nao foi possivel instalar openpyxl/reportlab.
    echo A aba Relatorios vai funcionar, mas XLSX e PDF nao serao gerados.
)

echo Gerando Painel AUTOMATA.exe...
if exist "build" rmdir /s /q "build"
if exist "dist\Painel AUTOMATA.exe" del /q "dist\Painel AUTOMATA.exe"
if exist "Painel AUTOMATA.spec" del /q "Painel AUTOMATA.spec"
if exist "painel_automata.spec" del /q "painel_automata.spec"

set CTK_IMPORTS=
if "%CTK_OK%"=="sim" set CTK_IMPORTS=--hidden-import customtkinter --hidden-import darkdetect

%PYTHON% -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "Painel AUTOMATA" ^
    --hidden-import win32print ^
    --hidden-import win32con ^
    --hidden-import win32api ^
    --hidden-import win32gui ^
    --hidden-import win32ui ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageTk ^
    %CTK_IMPORTS% ^
    --hidden-import openpyxl ^
    --hidden-import openpyxl.styles.numbers ^
    --hidden-import reportlab ^
    --hidden-import reportlab.pdfgen.canvas ^
    --hidden-import painel_ui ^
    --hidden-import imagens_api ^
    --hidden-import relatorios ^
    --hidden-import relatorio_export ^
    painel_automata.py

if errorlevel 1 (
    echo ERRO: falha ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo Copiando painel_automata_config.json para junto do exe...
copy /y "painel_automata_config.json" "dist\painel_automata_config.json" >nul
if not exist "dist\painel_automata_config.json" (
    echo AVISO: nao foi possivel copiar o config. Coloque o arquivo
    echo painel_automata_config.json manualmente ao lado do exe.
)

echo.
echo Pronto! EXE criado em:
echo %~dp0dist\Painel AUTOMATA.exe
echo.
echo IMPORTANTE: mantenha o arquivo painel_automata_config.json ao lado do
echo Painel AUTOMATA.exe (ele guarda URL/token da API e offsets).
echo Os modelos de relatorio sao salvos em painel_automata_relatorios.json
echo ao lado do exe e nao sao apagados ao atualizar o programa.
echo.
echo A aba Imagens agora tem duas visoes: Visualizador e Curadoria.
echo A Curadoria fala com o servidor de imagens pela chave "curadoria_url"
echo do painel_automata_config.json (padrao http://127.0.0.1:5050).
echo Se o painel roda em outra maquina que o servidor, ponha a URL dele ali.
pause