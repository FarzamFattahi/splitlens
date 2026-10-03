@echo off
cd /d "%~dp0"
if not exist node_modules (
  echo Run npm ci in this folder first. Node.js 22.12 or newer is required.
  pause
  exit /b 1
)
call npm run dev -- --open
