@echo off
setlocal
cd /d "%~dp0"
python presentation\ainook-author-gallery\serve.py --port 7889 %*
