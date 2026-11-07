@REM The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
@echo off
if not exist "%~dp0Index\python\pythonw.exe" (
  echo The Index of Azeroth needs the Index folder that came in its zip. Unpack the whole zip and start the Index again.
  pause
  exit /b 1
)
start "" "%~dp0Index\python\pythonw.exe" "%~dp0Index\launcher\start.py"
