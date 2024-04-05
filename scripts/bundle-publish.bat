@echo off
call python install/src/__main__.py --mode=bundle --interactive --no-hold && (
    call python install/src/__main__.py --mode=publish --interactive --no-hold
)

pause
