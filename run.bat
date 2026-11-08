@echo off
REM Starts ServiceHub on port 29880 (syncs .venv with uv on each run), or deploys it to the server.
REM LABEL: ServiceHub
REM DESCRIPTION: One admin page for every model and tool service.
cd /d "%~dp0"
if /i "%~1"=="run" goto run
if /i "%~1"=="deploy" goto deploy

:menu
echo.
echo ServiceHub
echo.
echo   1  Run the hub
echo   2  Deploy ^(publish to live, push .env, release^)
echo   Q  Quit
echo.
choice /c 12Q /n /m "What do you want to do? "
if errorlevel 3 exit /b 0
if errorlevel 2 goto deploy

:run
uv sync
if errorlevel 1 (
    echo uv sync failed. Install uv: winget install astral-sh.uv
    pause
    exit /b 1
)
uv run python src/app.py
if errorlevel 1 (
    echo.
    echo ServiceHub stopped with an error. Port 29880 busy? Is uv missing? ^(winget install astral-sh.uv^)
    pause
)
exit /b 0

rem ---- Deploy: publish the code to the live branch and/or copy the git-ignored .env to the
rem deployment machine in ONE ssh session (one password prompt).
rem The server refuses root over ssh, so we log in as a normal user. If the copy cannot write,
rem option 6 copies the one-time "chown" command and opens the server's web terminal (root shell).
rem Override the target: set DEPLOY_HOST / DEPLOY_DIR / DEPLOY_WEB_PORT before running, or put KEY=VALUE lines in the
rem git-ignored tools\deploy.local.ini (copy tools\deploy.local.example.ini) so the address stays out of the repository.
:deploy
setlocal enabledelayedexpansion
if exist "%~dp0tools\deploy.local.ini" for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0tools\deploy.local.ini") do set "%%A=%%B"
if not defined DEPLOY_HOST set "DEPLOY_HOST=lex@scutiserver1.local"
if not defined DEPLOY_DIR set "DEPLOY_DIR=/media/ZimaOS-HD/Apps/Applications/ServiceHub"
if not defined DEPLOY_WEB_PORT set "DEPLOY_WEB_PORT=7681"
for %%I in ("%~dp0.") do set "ROOT=%%~fI"

:d_menu
echo.
echo Target: %DEPLOY_HOST%:%DEPLOY_DIR%
echo.
echo   1  Publish code to the live branch
echo   2  Push .env to the server
echo   3  Both (publish, then push)
echo   4  Preview publish ^(dry run^)
echo   5  Preview push ^(dry run^)
echo   6  Fix server folder permissions ^(chown helper^)
echo   R  Release ^(publish to live, then tag VERSION^)
echo   Q  Quit
echo.
choice /c 123456RQ /n /m "What do you want to do? "
set "PICK=%errorlevel%"
if %PICK%==8 exit /b 0
if %PICK%==1 call :d_publish
if %PICK%==2 call :d_push
if %PICK%==3 call :d_publish && call :d_push
if %PICK%==4 call :d_publish --dry-run
if %PICK%==5 call :d_push --dry-run
if %PICK%==6 call :d_fixperms
if %PICK%==7 call :d_publish --release
goto d_menu

rem :d_publish [--dry-run | --release]
:d_publish
py "%ROOT%\tools\publish_live.py" %*
if errorlevel 1 (echo Publish failed. & exit /b 1)
if /i not "%~1"=="--dry-run" call :d_reminder "Code is on the live branch. On the server:" "git pull"
exit /b 0

rem :d_push [--dry-run]
rem Packs every existing file into one tar stream and unpacks it over a single ssh connection,
rem so the password is asked once.
:d_push
set "DRY="
if /i "%~1"=="--dry-run" set "DRY=1"
set "LIST=%TEMP%\servicehub_push.txt"
type nul > "%LIST%"
set /a COUNT=0
call :d_add ".env"
echo.
if !COUNT!==0 (echo Nothing to send. & del "%LIST%" & exit /b 0)
if defined DRY (echo Would send !COUNT! file^(s^). & del "%LIST%" & exit /b 0)
echo Sending !COUNT! file^(s^) in one ssh session. Enter the password once.
tar -cf - -C "%ROOT%" -T "%LIST%" | ssh "%DEPLOY_HOST%" "tar -xf - --no-same-permissions -C '%DEPLOY_DIR%'"
set "RC=!errorlevel!"
del "%LIST%"
if not "!RC!"=="0" (
    echo.
    echo FAILED. Nothing may have been copied. Check the error above.
    echo If it says Permission denied, press Y to run the chown helper, then run this option again.
    choice /c YN /n /m "Run the chown helper now? "
    if !errorlevel!==1 call :d_fixperms
    exit /b 1
)
echo Done.
call :d_reminder ".env is on the server. In the web terminal:" "docker compose up -d --build" "(run git pull here first if the code changed)"
exit /b 0

rem :d_add <path relative to the ServiceHub root, same path on the server>
:d_add
if not exist "%ROOT%\%~1" (echo skip    %~1 ^(missing locally^) & exit /b 0)
>>"%LIST%" echo %~1
set /a COUNT+=1
echo %~1
exit /b 0

rem The server's ssh user cannot chown by itself; root only exists in the web terminal.
rem Copies the command to the clipboard and opens that terminal: paste, Enter.
:d_fixperms
for /f "tokens=1,2 delims=@" %%U in ("%DEPLOY_HOST%") do (set "SVUSER=%%U" & set "SVHOST=%%V")
set "FIXCMD=chown -R %SVUSER% %DEPLOY_DIR%"
echo %FIXCMD%| clip
echo.
echo Copied to the clipboard:
echo   %FIXCMD%
echo Opening http://%SVHOST%:%DEPLOY_WEB_PORT%/ ^(root shell^). Paste the command there and press Enter.
start "" "http://%SVHOST%:%DEPLOY_WEB_PORT%/"
exit /b 0

rem :d_reminder <heading> <command> [note]
:d_reminder
echo.
echo ---- NEXT ON THE SERVER ----
echo %~1
echo   cd %DEPLOY_DIR%
set "SHOWCMD=%~2"
echo   !SHOWCMD!
if not "%~3"=="" echo   %~3
echo ----------------------------
exit /b 0
