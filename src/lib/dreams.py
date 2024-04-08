#!/bin/env python3
from http.client import HTTPSConnection
import os
import json
import hashlib
import math
from pathlib import Path
import platform
import subprocess
from typing import NamedTuple
from urllib.parse import urlparse

_no_color_print = False

class Color:
    GREY   = "\033[0;90m"
    RED     = "\033[0;31m"
    GREEN   = "\033[0;32m"
    YELLOW  = "\033[0;33m"
    BLUE    = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN    = "\033[0;36m"
    WHITE   = "\033[0;37m"
    RESET   = "\033[0m"

    def from_int(value:int) -> str:
        return f"\033[0;{value}m"

    def color(str:str, color:str):
        return color+str+Color.RESET if not _no_color_print else str

class DirNames:
    CONFIG = "config"
    CRASH = "crash-reports"
    INSTALL = "install"
    LOGS = "logs"
    MODS = "mods"
    RESOURCE_PACKS = "resourcepacks"
    SAVES = "saves"
    SHADERPACKS = "shaderpacks"
    DEFAULTS = f"{INSTALL}/defaults"
    RELEASES = f"{INSTALL}/releases"
    REPORTS = f"{INSTALL}/reports"
    PATCHNOTES = f"{INSTALL}/version"
    SERVER = f"{INSTALL}/server"
    FILE_MANIFEST = f"{INSTALL}/dreams-manifest.json"
    FILE_CONFIG = f"{INSTALL}/config.json"
    FILE_CONFIG_PUBLICATION = f"{INSTALL}/publish.json"
    FILE_CONFIG_SERVER = f"{SERVER}/serverconfig.json"
    FILE_VERSION_CONTENT = f"{PATCHNOTES}/version_content.txt"
    FILE_SERVER_MARKER = f"{SERVER}/is-server.json"
    FILE_VERSION_CHECKER = f"{CONFIG}/bcc.json"

class ConfigType(NamedTuple):
    # if true use client config
    # if false use server config
    is_client: bool
    # if true use local config,
    # if false use remote
    is_local: bool

closing_tasks = []

class ServerLocation:
    LATEST_META = "/latest.json"
    LATEST_ARCHIVE = "/latest.zip"
    VERSIONS = "/versions"

def get_location() -> str:
    path = f"{os.getcwd()}/install".replace("\\","/").split("/")
    manifest_name = DirNames.FILE_MANIFEST[DirNames.FILE_MANIFEST.rfind("/")+1:len(DirNames.FILE_MANIFEST)]

    for i in range (len(path),0,-1):
        sub = "/".join(path[0:i])
        if not os.path.isdir(sub):
            continue
        if manifest_name in os.listdir(sub+"/"):
            return sub
    raise FileNotFoundError("the manifest file could not be found in order to determine root")

def get_minecraft_dir() -> str:
    base = os.getcwd()
    try:
        base = get_location()
    except:
        pass
    split = base.replace("\\","/").split("/")
    for i in range(len(split)-1,0,-1):
        step = split[i]
        if step == ".minecraft":
            return "/".join(split[0:i])
    # .minecraft not found by recursion, trying
    # to find it in the user home directory
    
    os_name = platform.platform()
    home = Path.home()
    if os_name.startswith("Windows"):
        mc_dir = f"{home}/AppData/Roaming/.minecraft"
        if os.path.isdir(mc_dir) and len(os.listdir(mc_dir)) > 0:
            return mc_dir.replace("\\","/")
    elif os_name.startswith("Linux"):
        check_dirs = [
            f"{home}/.minecraft",
            f"{home}/.var/app/com.mojang.Minecraft/.minecraft"
        ]
        for dr in check_dirs:
            if os.path.isdir(dr) and len(os.listdir(dr)) > 0:
                return dr
    
    return None
        

_ROOT = "."
try:
    _ROOT = os.path.dirname(get_location()).replace("\\","/")
except FileNotFoundError:
    _ROOT = os.getcwd()
    pass

def get_root() -> str:
    return _ROOT

def get_manifest(root=get_root()) -> dict:
    path = f"{root}/{DirNames.FILE_MANIFEST}"
    with open(path,"r") as fp:
        return json.load(fp)
    
def get_as_path(file:str, root=get_root()) -> str:
    """returns the path to the file or directory within the profile root ({root}/{file})"""
    flatten = file.replace("\\","/")
    return f"{root}/{flatten}" if not flatten.startswith(root) else flatten

def get_config(
        root=get_root(), 
        type=ConfigType(True,True),
        remote_root=None
        ) -> dict:
    config = dict()
    rel_config = (
            DirNames.FILE_CONFIG
        if type.is_client else 
            DirNames.FILE_CONFIG_SERVER
        )
    if type.is_local:
        path = get_as_path(rel_config,root=root)
        try:
            with open(path,"r") as fp:
                config = json.load(fp)
        except:
            pass
    else:
        if remote_root is None or len(remote_root) < 1:
            raise ConnectionRefusedError(f"remote '{remote_root}' does not exist")
        parsed = urlparse(remote_root)
        split = remote_root.split("/")
        domain = parsed.netloc
        resource = f"{parsed.path}/{rel_config}"
        connection = HTTPSConnection(domain, timeout=180)
        # first, get the latest version
        connection.request("GET",resource)
        with connection.getresponse() as response:
            if response.status == 200:
                try:
                    resp = response.read()
                    config = json.loads(resp.decode("UTF-8"))
                except:
                    pass
        connection.close()
    return config

def get_config_option(
        key:str,
        default=None,
        overrides=[
            get_config(type=ConfigType(True,True))
        ]
        ):
    """
    for server override behaviour :
    ```
    overrides=[
        get_config(type=ConfigType(False,True)),
        get_config(type=ConfigType(True,True))
    ]
    ```
    """
    for d in overrides:
        if key in d:
            return d[key]
    return default

def get_current_config_type() -> ConfigType:
    # in order :
    # 1. local or remote ?
    #       check on local config if anything forces local
    # 2. client or server ?
    is_local = get_config_option(
        "force-local-config",
        False,
        overrides=[
            get_config(type=ConfigType(False,True)),
            get_config(type=ConfigType(True,True))
        ]
    )
    is_client = not (os.path.isfile(get_as_path(DirNames.FILE_SERVER_MARKER)) and os.path.isfile(get_as_path(DirNames.FILE_CONFIG_SERVER)))

    return ConfigType(is_client, is_local)


def is_excluded(path:str, exclude:list) -> bool:
    root = get_root()
    cleaned = path.replace("\\","/").replace(f"{root}/","")
    return (
        cleaned in exclude
        or any(f for f in exclude if cleaned.startswith(f))
    )

def list_content(root:str, include=["/"], exclude=[]) -> list:
    """Returns a list of relative paths to all the files found.

    `root` : the root directory where to start the search
    `include` : a list of directories to search (relatively to `path`)
    `exclude` : a list of directories and files to ignore (relatively to `path`)"""

    content = []
    for path in include:
        cleaned = path if not path.endswith("/") or path.endswith("\\") else path[0:len(path)-1]
        absolute = get_as_path(cleaned)
        if os.path.isfile(absolute) and not cleaned in content:
            content.append(cleaned.replace("\\","/"))
        elif os.path.isdir(absolute):
            for w_root,_,files in os.walk(absolute):
                root_name = w_root.replace(f"{root}/","")
                if is_excluded(root_name,exclude):
                    continue
                for file in files:
                    rel_file = f"{root_name}/{file}"
                    if is_excluded(rel_file,exclude) or rel_file in content:
                        continue
                    content.append(rel_file.replace("\\","/"))
    return content

def get_file_hash(absolute_file:str) -> str:
    h = hashlib.md5()
    with open(absolute_file, 'rb') as f:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            chunk = f.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def print_progess_bar(
        progress:float, 
        length:int, 
        prepend="[", 
        append="] {:.1%}",
        fill="━",
        empty="·",
        current=" ",
        adapt_size=True,
        prepend_end=None,
        append_end="] done!",
        fill_color=Color.from_int(92),
        current_color=Color.from_int(92),
        empty_color=Color.GREY,
        done_color=Color.CYAN
        ):
    """Styles :
    classic: 
        fill="━", 
        empty="·", 
        current=" "
    pacman: 
        fill="-", 
        empty="·", 
        current=" ᗧ"
    """
    term_width = 1920
    try:
        term_width = os.get_terminal_size()[0]
    except:
        pass
    c_progess = min(max(progress,0),1)
    last_iter = c_progess == 1

    append = append.format(progress)

    resized_length = length
    pre = prepend_end if last_iter and not prepend_end is None else prepend
    app = append_end if last_iter and not append_end is None else append
    barless_content = f"{pre}{app}"
    if adapt_size:
        resized_length = min(length,max(2,term_width-len(barless_content)))
    empty_length = math.floor((1-c_progess)*resized_length)
    fill_length = math.ceil(c_progess*resized_length)
    fill_str = (f"{(fill_length-len(current))*fill}{current}" if not last_iter else fill_length*fill) if fill_length > 0 else ""
    raw_bar = f"{pre}{fill_str}{empty_length*empty}{app}"
    bar = f"{pre}{Color.color(fill_str,fill_color)}{Color.color(empty_length*empty,empty_color)}{app}"
    if last_iter:
        bar = f"{pre}{Color.color(f'{fill_str}{empty_length*empty}',done_color)}{app}"
    print(
        bar + (" "*max(0,term_width-len(raw_bar))),
        end="\r" if not last_iter else "\n"
        )

def byte_str(bytes:int, unit_name="auto", unit_byte_amount=-1, number_format="auto") -> str:
    format = number_format
    divider = unit_byte_amount
    unit = unit_name
    if unit_name == "auto":
        unit_match = {
            "b": 1,
            "Kb": 1000,
            "Mb": 1000*1000,
            "Gb": 1000*1000*1000,
            "Tb": 1000*1000*1000*1000
        }
        sorted_units = sorted(unit_match.keys(), key=lambda x: unit_match.get(x,0))
        unit = sorted_units[0]
        for next_unit in sorted_units[1:len(sorted_units)]:
            if bytes >= unit_match[next_unit]:
                unit = next_unit
            else:
                break
        divider = unit_match[unit]
    amount = bytes/divider
    if number_format == "auto":
        format = "{:.1f}" if amount < 10 else "{:.0f}"
    return f"{format.format(amount)} {unit}"

def accept_answer(
        answer:str, 
        default=True, 
        default_if_empty=True, 
        accept=["yes", "y", "ok"],
        reject=["no", "n"]
    ) -> bool:
    if len(answer) == 0 and default_if_empty:
        return default
    if answer.lower() in accept:
        return True
    elif answer.lower() in reject:
        return False
    return None

def ask_user(
        prompt:str,
        accept_option="y",
        reject_option="n",
        accept_alt=["yes","ok"],
        reject_alt=["no", "clearly, with all due respect, NO!"],
        default_accept=True,
        max_tries = 32
        ) -> bool:
    first_op = accept_option.upper() if default_accept else reject_option.upper()
    alt_op = reject_option if default_accept else accept_option
    full_prompt = f"{prompt} [{first_op}/{alt_op}] : "
    for _ in range(0,max_tries):
        answer = input(full_prompt)
        response = accept_answer(
            answer,
            default=default_accept,
            default_if_empty=True,
            accept=[accept_option,*accept_alt],
            reject=[reject_option,*reject_alt]
            )
        if response is None:
            print(f"\"{answer}\" is not a valid option")
        else:
            return response
    raise ValueError("max tries exceeded")

def add_closing_task(task):
    closing_tasks.append(task)

def execute_closing_tasks(fail_on_error=False):
    for task in closing_tasks:
        try:
            subprocess.Popen(
            task,
            shell=True
            )
        except RuntimeError as r:
            if fail_on_error:
                raise r
