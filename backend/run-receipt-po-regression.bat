@echo off
setlocal EnableExtensions
cd /d "%~dp0"
python run-tests.py receipt-po-regression %*
