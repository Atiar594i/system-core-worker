@echo off
title Flex SMS Live Hub Server
cd /d "%~dp0"
echo ========================================================
echo     Starting Flex SMS Live Hub Server...
echo ========================================================
start "" http://localhost:5000
python server.py
pause
