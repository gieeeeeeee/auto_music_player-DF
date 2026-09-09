@echo off
rem 以管理员身份运行自动演奏器(游戏以管理员运行时,普通权限的按键会被系统丢弃)
cd /d "%~dp0"
python main.py
pause
