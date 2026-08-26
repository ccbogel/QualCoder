@echo off
setlocal enabledelayedexpansion
title Compile .ui to .py (pyuic6)

REM Usage: compile_ui_Windows.bat [ui_folder] [output_folder]
REM Arg 1: folder holding the .ui files (default: current folder)
REM Arg 2: output folder (default: next to each .ui file)

REM ==================== Config ====================
set "UI_DIR=%~1"
if not defined UI_DIR set "UI_DIR=%CD%"
set "OUT_DIR=%~2"

set "RECURSE=1"          REM 1 = walk subfolders
set "DRYRUN=0"           REM 1 = report only, write nothing
set "PY=python"          REM interpreter of the active venv
set "PYUIC_ARGS="        REM extra pyuic6 flags, e.g. --from-imports
set "MIN_SIZE=200"       REM reject suspiciously small output

REM ==================== Checks ====================
for %%A in ("%UI_DIR%") do set "ROOT=%%~fA"
if not exist "%ROOT%\" (
    echo [ERROR] Folder not found: %ROOT%
    goto :end
)

%PY% -c "import PyQt6.uic" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyQt6 not importable with "%PY%". Activate the venv first.
    goto :end
)

for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
set "BACKUP=%ROOT%\_ui_backup_%STAMP%"
set "LOG=%ROOT%\_ui_compile_%STAMP%.log"
set "OK=0"
set "FAIL=0"
set "SAME=0"

echo Source : %ROOT%
if defined OUT_DIR (echo Output : %OUT_DIR%) else (echo Output : same folder as each .ui)
echo Backup : %BACKUP%
echo Log    : %LOG%
echo.
>"%LOG%" echo === compile .ui to .py  %DATE% %TIME% ===

REM ==================== Main loop ====================
if "%RECURSE%"=="1" (
    for /r "%ROOT%" %%F in (*.ui) do call :compile "%%~fF"
) else (
    for %%F in ("%ROOT%\*.ui") do call :compile "%%~fF"
)

echo.
echo Compiled: !OK!   Unchanged: !SAME!   Failed: !FAIL!
>>"%LOG%" echo === compiled=!OK! unchanged=!SAME! failed=!FAIL! ===
if !FAIL! GTR 0 echo Check the log for details.
goto :end

REM ==================== Subroutine ====================
:compile
set "SRC=%~1"
set "BASE=%~n1"
set "SRCDIR=%~dp1"
set "REL=!SRCDIR:%ROOT%\=!"
if defined OUT_DIR (set "DEST_DIR=%OUT_DIR%\!REL!") else (set "DEST_DIR=!SRCDIR!")
set "DEST=!DEST_DIR!!BASE!.py"
set "TMP=!DEST!.new"

if "%DRYRUN%"=="1" (
    echo [DRY] !BASE!.ui
    >>"%LOG%" echo DRY  !SRC!
    goto :eof
)

if not exist "!DEST_DIR!" md "!DEST_DIR!" >nul 2>&1

REM Write to a temp file first, so a failed run never truncates the old .py
%PY% -m PyQt6.uic.pyuic %PYUIC_ARGS% "!SRC!" -o "!TMP!" 2>>"%LOG%"
if errorlevel 1 goto :failed
if not exist "!TMP!" goto :failed
for %%S in ("!TMP!") do set "SIZE=%%~zS"
if !SIZE! LSS %MIN_SIZE% goto :failed

REM Skip identical output: no backup, no rewrite
if exist "!DEST!" (
    fc /b "!TMP!" "!DEST!" >nul 2>&1
    if not errorlevel 1 (
        del /q "!TMP!"
        set /a SAME+=1
        echo [ =  ] !BASE!.py unchanged
        >>"%LOG%" echo SAME !DEST!
        goto :eof
    )
    if not exist "%BACKUP%\!REL!" md "%BACKUP%\!REL!" >nul 2>&1
    copy /Y "!DEST!" "%BACKUP%\!REL!" >nul
    if errorlevel 1 (
        echo [ERR ] backup failed, skipping !BASE!.py
        >>"%LOG%" echo FAIL backup !DEST!
        del /q "!TMP!"
        set /a FAIL+=1
        goto :eof
    )
)

move /Y "!TMP!" "!DEST!" >nul
if errorlevel 1 goto :failed
set /a OK+=1
echo [ OK ] !BASE!.py
>>"%LOG%" echo OK   !SRC! to !DEST!
goto :eof

:failed
if exist "!TMP!" del /q "!TMP!"
set /a FAIL+=1
echo [ERR ] !BASE!.ui  (previous .py kept)
>>"%LOG%" echo FAIL !SRC!
goto :eof

:end
echo.
pause
endlocal
