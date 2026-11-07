@REM The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
@echo off
if not exist "%~dp0Index\python\python.exe" (
  echo The Index of Azeroth needs the Index folder that came in its zip to remove itself. Delete the IndexOfAzeroth folder by hand.
  pause
  exit /b 1
)
"%~dp0Index\python\python.exe" "%~dp0Index\launcher\uninstall.py" & exit /b
