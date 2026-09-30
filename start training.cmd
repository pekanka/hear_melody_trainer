@echo off
set "APP=%~dp0melody_ear_trainer.py"
set "PYTHONW=C:\Users\pekanka\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if not exist "%PYTHONW%" (
  echo Python not found. Install Python with Tkinter, then run melody_ear_trainer.py.
  pause
  exit /b 1
)
start "" "%PYTHONW%" "%APP%"
