@echo off
setlocal
cd /d "%~dp0"
uv run python preview.py --background ".\backgrounds\B.png" %*
