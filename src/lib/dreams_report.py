#!/bin/env python3
import os
from zipfile import ZipFile
from os import path
import lib.dreams as dreams
from lib.dreams import DirNames, get_as_path
from datetime import datetime

class ReportContent:
    LATEST = "latest.log"
    DEBUG = "debug.log"
    CRASH = "crash_report"

def create_report(output_dir:str, include:list, verbose=True, note="") -> str:
    # The time difference allowed between the last 
    # modification of latest.log and the latest crash 
    # report to consider them as being part of the 
    # same session (in seconds).
    # This should be 0 but we'll allow a bit of tolerance.
    crash_report_time_window = 5

    root = dreams.get_root()
    logfile = f"{get_as_path(DirNames.LOGS)}/{ReportContent.LATEST}"

    if not path.isfile(logfile):
        if verbose: print("no log to report")
        return

    if not path.isdir(output_dir):
        os.mkdir(output_dir)

    report_content = []
    if ReportContent.LATEST in include:
        if verbose: print(f"adding {logfile.replace(f'{root}/','')} to report...")
        report_content.append(logfile)
    if ReportContent.DEBUG in include:
        debug = f"{get_as_path(DirNames.LOGS)}/{ReportContent.DEBUG}"
        if verbose: print(f"adding {debug.replace(f'{root}/','')} to report...")
        report_content.append(debug)
    if ReportContent.CRASH in include and path.isdir(f"{get_as_path(DirNames.CRASH)}"):
        last_launch = path.getmtime(logfile)
        reports = sorted(os.listdir(f"{get_as_path(DirNames.CRASH)}"),reverse=True)
        if len(reports) > 0:
            crash = reports[0]
            latest_crash = f"{get_as_path(DirNames.CRASH)}/{crash}"
            last_launch = path.getmtime(logfile)
            crash_date = datetime.strptime(crash[crash.find("-")+1:crash.rfind("-")],"%Y-%m-%d_%H.%M.%S")
            if not abs(crash_date.timestamp()-last_launch) > crash_report_time_window:
                if verbose: print(f"adding {latest_crash.replace(f'{root}/','')} to report...")
                report_content.append(latest_crash)

    out_path = None
    with ZipFile(f"{output_dir}/report-{datetime.now().strftime('%Y-%m-%d_%H.%M.%S')}.zip","w") as zipfile:
        for f in report_content:
            zipfile.write(f,arcname=f[f.replace("\\","/").rfind("/")+1:len(f)])
        if len(note) > 0:
            zipfile.writestr("note.txt",note)
        out_path = zipfile.filename
    return out_path

def main(args:list):
    #################################################

    # What to include in the report
    report_include = {
        ReportContent.LATEST: True,
        ReportContent.DEBUG: True,
        ReportContent.CRASH: True
    }

    # Where the report zip file should be stored (relative to profile)
    report_destination = get_as_path(DirNames.REPORTS)

    # Report upload message URL (if empty the message will be ignored)
    upload_url = ""

    #################################################

    if not any(k for k in report_include.values()):
        print("Please include at least one element in the report.\nAborting report....")
        return
    
    note = ""
    if (
        not (
        "--no-note" in args 
        or "-n" in args 
        or not report_include.get("note",True)
        )
        and "--interactive" in args
        and not "--note=" in args
        ):
        note = input("""Thank you for submitting a report!
    Please write a note describing what went wrong (you can also leave this blank) :\n    """)
    
    for a in args:
        if a.startswith("--note="):
            note = a.replace("--note=").replace("\"","")
            break

    out = create_report(report_destination, [k for k,v in report_include.items() if v],verbose=True, note=note)
    if out is None:
        return

    print(f"\nreport created at:\n{out.replace('/',os.sep)}")

    print("\nSend this report to the modpack creator to allow them to troubleshoot your problem.")

    if len(upload_url) > 0:
        print(f"You can upload your crash report to: \n{upload_url}")
    print("")

if __name__ == "__main__":
    main(os.sys.argv)
