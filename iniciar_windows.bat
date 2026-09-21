@echo off
chcp 65001 > nul
title Monitor de Precos de Fornecedores
cd /d "%~dp0"

echo ============================================
echo   MONITOR DE PRECOS - FORNECEDORES
echo ============================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.10+ ou use o executavel gerado com PyInstaller.
    echo.
    pause
    exit /b 1
)

python monitor_precos.py

echo.
echo ============================================
echo   Execucao finalizada. Veja monitor.log
echo ============================================
echo.
pause
