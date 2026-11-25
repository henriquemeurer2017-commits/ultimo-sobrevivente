@echo off
REM Abre o Ultimo Sobrevivente com duplo clique.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PY%" set "PY=pythonw"
start "" "%PY%" "%~dp0jogo.py"
