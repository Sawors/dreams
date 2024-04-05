@echo off

rem ######################[EDIT THIS]########################

rem Add '--no-color' if your terminal does not support colors
set toolkit_args=--interactive

rem #########################################################

setlocal ENABLEDELAYEDEXPANSION
set temp_dir=%TEMP%\8kWM6NkLQ3VUk3WfVOmEKL216vVFrwOL
set repo=https://github.com/Sawors/dreams/archive/refs/heads/master.zip
set output=%temp_dir%\toolkit.zip
set exec=python
set src_dir=.\install\src
set entry_point=__main__.py

rem embedded python relative data
set em_python_dir=install\_python
set em_python_exec=python.exe
set em_python_source=https://www.python.org/ftp/python/3.12.1/python-3.12.1-embed-amd64.zip
set em_python_dl=%temp_dir%\python_runtime.zip

mkdir %temp_dir%

if exist %src_dir%\%entry_point% (
    echo Upgrading toolkit...
) else (
    echo Installing toolkit...
)

curl -LJ %repo% -o "%output%"
powershell Expand-Archive -LiteralPath '%output%' -DestinationPath '%CD%' -Force
del %output%

if exist %src_dir%\%entry_point% (
    echo Toolkit successfully installed !

    rem check if python is present
    if exist %em_python_dir%\%em_python_exec% (
        echo Embedded python install found, switching to using it.
        for %%i in ("%em_python_dir%\%em_python_exec%") do SET "exec=%%~fi"
    )

    rem if python does not work: install an embedded version
    "!exec!" --version >nul 2>&1 || (
        echo Python not installed, installing an embedded version...
        curl %em_python_source% -o "%em_python_dl%"
        powershell Expand-Archive -LiteralPath '%em_python_dl%' -DestinationPath '%temp_dir%' -Force
        del %src_dir%
        move %temp_dir%\dreams-master\src %src_dir%
        del '%em_python_dl%'
        for %%i in ("%em_python_dir%\%em_python_exec%") do SET "exec=%%~fi"
    )

    del %temp_dir%

    "!exec!" --version >nul 2>&1 || (
        echo Python install failed, aborting...
        exit /b 9009
    )
    echo Automatically starting its execution...
    call "!exec!" %src_dir%\%entry_point% %toolkit_args%
) else (
    echo Download failed, aborting.
    del %temp_dir%
    exit /b 1
)
