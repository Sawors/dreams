@echo off
setlocal ENABLEDELAYEDEXPANSION

rem ######################[EDIT THIS]########################

rem Add '--no-color' if your terminal does not support colors
set toolkit_args=--interactive

rem #########################################################

set temp_dir=%TEMP%\8kWM6NkLQ3VUk3WfVOmEKL216vVFrwOL
set repo=https://github.com/Sawors/dreams/archive/refs/heads/master.zip
set output=%temp_dir%\toolkit.zip
set exec=python
set src_dir=.\install\src
set entry_point=__main__.py

rem embedded python relative data
set em_python_dir=install\runtime
set em_python_exec=python.exe
set em_python_source=https://www.python.org/ftp/python/3.12.1/python-3.12.1-embed-amd64.zip
set em_python_dl=%temp_dir%\python_runtime.zip

mkdir %temp_dir% >nul 2>&1

if exist %src_dir%\%entry_point% (
    echo Upgrading toolkit...
) else (
    echo Installing toolkit...
)

curl -LJ %repo% -o "%output%"
powershell Expand-Archive -LiteralPath '%output%' -DestinationPath '%temp_dir%' -Force >nul 2>&1
del /F /S /Q %src_dir% >nul 2>&1
rmdir /S /Q %src_dir% >nul 2>&1
mkdir .\install >nul 2>&1
move /y "%temp_dir%\dreams-master\src" ".\install" >nul 2>&1
rem move /y "%temp_dir%\dreams-master\scripts\toolkit.bat" ".\" >nul 2>&1
del /F /S /Q %output% >nul 2>&1

if exist %src_dir%\%entry_point% (
    echo Toolkit successfully installed !

    rem check if embedded python is present
    if exist %em_python_dir%\%em_python_exec% (
        echo Embedded python install found, switching to using it.
        for %%i in ("%em_python_dir%\%em_python_exec%") do SET "exec=%%~fi"
    )

    rem if python does not work: install an embedded version
    "!exec!" --version >nul 2>&1 || (
        echo Python not installed, installing an embedded version...
        curl %em_python_source% -o "%em_python_dl%"
        powershell Expand-Archive -LiteralPath '%em_python_dl%' -DestinationPath '%temp_dir%\runtime' -Force >nul 2>&1
        move /y "%temp_dir%\runtime" ".\install" >nul 2>&1
        for %%i in ("%em_python_dir%\%em_python_exec%") do SET "exec=%%~fi"
    )

    del /F /S /Q %temp_dir% >nul 2>&1
    rmdir /S /Q %temp_dir% >nul 2>&1

    "!exec!" --version >nul 2>&1 || (
        echo Python install failed, aborting...
        exit /b 9009
    )
    echo:
    echo ------------------------------------------------------------------
    echo        Toolkit installed and ready, starting execution...
    echo:
    call "!exec!" %src_dir%\%entry_point% %toolkit_args%
) else (
    echo Download failed, aborting.
    del /F /S /Q %temp_dir% >nul 2>&1
    rmdir /S /Q %temp_dir% >nul 2>&1
    exit /b 1
)
