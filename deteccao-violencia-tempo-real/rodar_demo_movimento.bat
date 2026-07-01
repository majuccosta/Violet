@echo off
REM Plano B garantido: detector de movimento (so OpenCV) ao vivo
cd /d "%~dp0"
"%LOCALAPPDATA%\Python\bin\python.exe" deteccao_movimento_tempo_real.py
pause
