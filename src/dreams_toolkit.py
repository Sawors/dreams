#!/bin/env python3
from __future__ import print_function
import os, platform
import lib.dreams, lib.dreams_bundle, lib.dreams_install, lib.dreams_report, lib.dreams_upgrade
from lib.dreams import Color

class RunMode:
    INSTALL = "install"
    UPGRADE = "upgrade"
    REPORT = "report"
    BUNDLE = "bundle"

args_help_text = """Command line arguments :

    GLOBAL:
    --help           show this help message
    --mode=<mode>    set the mode to use
    --interactive    force an interactive session
    --no-interact    prevent an interactive session from starting
    --server         will try to force server mode
    --client         will try to force client mode
    --no-color       will disable color printing to console
    --no-hold        will close the script when done, even on interactive mode

    INSTALL:
    --repo=<url>, -r set the repository from which the modpack should be
                     downloaded
    --server, -s     use a custom installation process made for servers
    --import, -o     import the option.txt, resourcepacks/ and
                     shaderpacks/ from the .minecraft if it can be found
    --interactive    will ask the user for what to import and if the
                     installation should proceed

    UPGRADE:
    --server, -s     use a custom installation process made for servers
    --interactive    will print the patchnote and ask the user whether 
                     the upgrade should proceed or not

    REPORT:
    --no-note, -n    similar to --no-interact in this case, skip the
                     "insert note" prompt
    --note=<note>    adds a custom note and skip the promp

    BUNDLE:
    --archive, -a    bundle the modpack as a zip archive instead of a directory
    --ophans, -o     print orphan config found and returns. 
                     This option does not bundle the modpack!
    --increment, -i  automatically try to increment the version based on
                     file changes
"""

def main(args):

    lib.dreams._no_color_print = "--no-color" in args

    available_modes_message = f"""Available modes are:

    [{Color.color('1',Color.CYAN)}] {Color.color(RunMode.INSTALL,Color.CYAN)} : install the modpack in the same directory as this program
    [{Color.color('2',Color.CYAN)}] {Color.color(RunMode.UPGRADE,Color.CYAN)} : upgrade the current installation to the latest version
    [{Color.color('3',Color.CYAN)}] {Color.color(RunMode.REPORT,Color.CYAN)}  : create a bug-report zip file
    [{Color.color('4',Color.CYAN)}] {Color.color(RunMode.BUNDLE,Color.CYAN)}  : bundle the modpack to a zip file
    
    or {Color.color('exit',Color.CYAN)} to exit this program"""

    mode = None
    mode_identifier = "--mode="

    if "--help" in args or "-h" in args:
        print(args_help_text)
        exit()
    
    interactive = "--interactive" in args

    for arg in args:
        if arg.startswith(mode_identifier):
            mode = arg[len(mode_identifier):len(arg)]
            args.remove(arg)
            break
        elif not arg.startswith("-"):
            mode = arg
            args.remove(arg)
            break
    
    print(f"{Color.GREY}{lib.dreams.get_root()}{Color.RESET}")

    if (not "--client" in args
        and not "--server" in args
        and os.path.isfile(lib.dreams.get_as_path(lib.dreams.DirNames.FILE_SERVER_MARKER))
    ):
        args.append("--server")
        print("\nServer install detected: using server mode by default. To force client mode, add the argument --client.\n")
    
    if lib.dreams_upgrade.is_standalone():
        # installing if dir is empty
        print("Modpack not installed, defaulting to install mode.")
        mode = RunMode.INSTALL
        interactive = True
        if not "--interactive" in args:
            args.append("--interactive")

    if mode is None and (
        not "--no-interact" in args 
        and not ("--server" in args or "-s" in args)
        ):
        interactive = True
        if not "--interactive" in args:
            args.append("--interactive")
        mode=input(f"Please enter the action you want to do.\n{available_modes_message}\n\nmode : ")
        
    match (str(mode).lower()):
        case RunMode.INSTALL | "1":
            print("installing...")
            lib.dreams_install.main([*args, "--standalone"])
        case RunMode.UPGRADE | "2":
            print("upgrading...")
            lib.dreams_upgrade.main(args)
        case RunMode.REPORT | "3":
            print("creating a report...")
            lib.dreams_report.main(args)
        case RunMode.BUNDLE | "4":
            print("bundling...")
            lib.dreams_bundle.main(args)
        case "exit" | "x":
            exit()
        case _:
            print(f"ERROR: mode \'{mode}\' is not regonized.")

    if interactive and not "--no-hold" in args:
        if platform.system() == "Windows":
            os.system("pause")
        else:
            os.system("/bin/bash -c 'read -s -n 1 -p \"Press any key to continue...\"'")
            print()

if __name__ == "__main__":
    main(os.sys.argv[1:len(os.sys.argv)])
