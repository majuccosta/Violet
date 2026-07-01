@echo off
REM Demo principal: o modelo treinado (.tflite) rodando ao vivo na webcam
cd /d "%~dp0"
"%LOCALAPPDATA%\Python\bin\python.exe" deteccao_tflite_tempo_real.py
pause
