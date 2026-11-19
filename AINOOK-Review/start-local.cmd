@echo off
setlocal
cd /d "%~dp0"
echo AINOOK local preview: http://127.0.0.1:7889/
where py >nul 2>nul
if errorlevel 1 (
  python -X utf8 -m ainook.site --port 7889 --no-scheduler
) else (
  py -3 -X utf8 -m ainook.site --port 7889 --no-scheduler
)
if errorlevel 1 pause
