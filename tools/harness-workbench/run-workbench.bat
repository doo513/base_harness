@echo off
rem =========================================================================
rem Base Harness Workbench Windows Launcher
rem Standard-library operator aid for Base Harness development.
rem =========================================================================
chcp 65001 > nul
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
if "%BASE_HARNESS_ROOT%"=="" set BASE_HARNESS_ROOT=%USERPROFILE%\Downloads\base_harness

rem 1. Check Python executable
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_EXE=python
    goto :RUN
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_EXE=py -3
    goto :RUN
)

rem Check common Windows Python install paths
if not "%HARNESS_WORKBENCH_PYTHON%"=="" if exist "%HARNESS_WORKBENCH_PYTHON%" (
    set PYTHON_EXE="%HARNESS_WORKBENCH_PYTHON%"
    goto :RUN
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :RUN
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :RUN
)
if exist "C:\Python312\python.exe" (
    set PYTHON_EXE="C:\Python312\python.exe"
    goto :RUN
)

echo [오류] Python을 찾을 수 없습니다. Windows 환경에 Python 3이 설치되어 있고 PATH에 등록되어 있는지 확인하십시오.
pause
exit /b 1

:RUN
rem If arguments provided, pass through to workbench.py
if not "%~1"=="" (
    %PYTHON_EXE% "%SCRIPT_DIR%workbench.py" %*
    exit /b %errorlevel%
)

rem Otherwise launch GUI by default
echo Base Harness Workbench 시작 중...
%PYTHON_EXE% "%SCRIPT_DIR%workbench.py" --gui --workspace "%SCRIPT_DIR%" --harness-root "%BASE_HARNESS_ROOT%"
if %errorlevel% neq 0 (
    echo.
    echo GUI 실행 중 오류가 발생했거나 GUI를 지원하지 않는 환경입니다.
    echo 진단 모드로 재시도합니다...
    %PYTHON_EXE% "%SCRIPT_DIR%workbench.py" --diagnose --workspace "%SCRIPT_DIR%" --harness-root "%BASE_HARNESS_ROOT%"
    pause
)
