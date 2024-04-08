#!/bin/env python3
import os
import shutil
import tempfile
from http.client import HTTPSConnection
from zipfile import ZipFile
import json
from datetime import datetime
from urllib.parse import urlparse
import lib.dreams as dreams
from lib.dreams import Color

DEFAULT_REPOSITORY_PATH = "https://sawors.net/modpacks"

class InstallMode:
    CLIENT = "client"
    SERVER = "server"

def get_latest_release_name(repo:str) -> tuple[str,str]:
    latest_version_name = None
    latest_version = None
    parsed = urlparse(repo)
    connection = HTTPSConnection(parsed.netloc, timeout=180)
    # first, get the latest version
    connection.request("GET",f"{parsed.path}{dreams.ServerLocation.LATEST_META}")
    with connection.getresponse() as response:
        if not response.status == 200:
            return None
        try:
            resp = response.read()
            data = json.loads(resp.decode("UTF-8"))
            latest_version = data.get("version",None)
            latest_version_name = data.get("version-name",None)
        except:
            pass
    connection.close()
    return (latest_version,latest_version_name)

# profile related functions
def generate_profile_data(manifest_data:dict, minecraft_dir:str) -> dict:
    mc_path = minecraft_dir if not minecraft_dir.replace("\\","/").endswith("/") else minecraft_dir.replace("\\","/")[:len(minecraft_dir.replace("\\","/"))-1]
    version_dir = f"{mc_path}/versions"
    profile_file = f"{mc_path}/launcher_profiles.json"
    if not (
        os.path.isdir(mc_path)
        and os.path.isdir(version_dir)
        and os.path.isfile(profile_file)
    ):
        raise OSError("Launcher files could not be found")
    target_modloader = manifest_data["modloader"]
    target_version = manifest_data["game-version"]
    fitting_versions = list(filter(lambda x: target_modloader.lower() in x and target_version.lower() in x, os.listdir(version_dir)))
    if len(fitting_versions) < 1:
        raise FileNotFoundError("Version could not be found")
    best_version = sorted(fitting_versions, reverse=True)[0]
    launcher_data = {}
    with open(profile_file, "r", encoding="UTF-8") as datain:
        launcher_data = json.load(datain)
    profiles = launcher_data["profiles"]
    now = datetime.now()
    millis = now.strftime("%f")[0:3]
    now_str = now.strftime(f"%Y-%m-%dT%H:%M:%S.{millis}z")

    custom_profile = {
        "created": now_str,
        "gameDir": dreams.get_root(),
        "icon": "Gold_Ore",
        "javaArgs" : "-Xmx6G -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M",
        "lastUsed": now_str,
        "lastVersionId": best_version,
        "name": manifest_data["name"],
        "type": "custom"
    }
    profile_name = f"{manifest_data['name']}-{manifest_data['game-version']}"
    profiles[profile_name] = custom_profile

    return json.dumps(
        launcher_data,
        indent=4
        )


def download_pack(url:str, download_location:str, verbose=True) -> str:
    _chunk_size = 1024*1024
    if os.path.isfile(download_location):
        raise FileExistsError("file already exists")
    dl_target = f"{download_location}{dreams.ServerLocation.LATEST_ARCHIVE}"
    parsed_url = urlparse(url)
    connection = HTTPSConnection(parsed_url.netloc, timeout=10)
    connection.request("GET", f"{parsed_url.path}{dreams.ServerLocation.LATEST_ARCHIVE}")
    with connection.getresponse() as response:
        headers = response.getheaders()
        length_header = [v for k,v in headers if k == "Content-Length"]
        total_size = int(length_header[0]) if len(length_header) > 0 else 1
        total_size_str = dreams.byte_str(total_size)
        downloaded = 0
        with open(dl_target, "ab") as data_output:
            last_percent = 0
            while chunk := response.read(_chunk_size):
                downloaded += len(chunk)
                if verbose:
                    progress = downloaded/total_size
                    percent = int(100*progress)
                    if percent > last_percent:
                        last_percent = percent
                        if verbose:
                            dreams.print_progess_bar(
                                progress,
                                50,
                                prepend=f"  downloading files: {dreams.byte_str(downloaded)}/{total_size_str} ["
                                )
                data_output.write(chunk)
    connection.close()
    return dl_target

def import_options(dest:str, import_list:list, override=True, verbose=True):
    
    minecraft_dir = dreams.get_minecraft_dir()
            
    if minecraft_dir is None or not os.path.isdir(minecraft_dir):
        raise RecursionError("source directory does not exist or could not be automatically determinated")
    if not os.path.isdir(dest):
        raise FileNotFoundError("target directory does not exist")

    import_content = []
    for f in import_list:
        source_path = f"{minecraft_dir}/{f}"
        if not os.path.exists(f"{minecraft_dir}/{f}"):
            print(f"{f} does not exist")
            continue
        if os.path.isdir(source_path):
            for root, _, files in os.walk(source_path):
                for file in files:
                    import_content.append(f"{root}/{file}")
        elif os.path.isfile(source_path):
            import_content.append(source_path)

    for index, f in enumerate(import_content):
        if verbose:
            name = f[f.rfind("/")+1:len(f)]
            dreams.print_progess_bar(
                (index+1)/len(import_content),
                50,
                f"  importing files: {(index+1)}/{len(import_content)} ["
            )
        dest_path = f.replace(minecraft_dir, dest)
        if os.path.exists(dest_path):
            if not override:
                continue
            os.remove(dest_path)
        if not os.path.isdir(os.path.dirname(dest_path)):
            os.makedirs(os.path.dirname(dest_path))
        shutil.copy(f, dest_path)



def install_pack(
        archive:str, 
        install_location:str, 
        install_defaults=True, 
        import_list=[], 
        verbose=True, 
        install_mode=InstallMode.CLIENT
        ):
    if not os.path.isfile(archive):
        raise FileNotFoundError("The archive specified does not exist.")

    install_exclude = []

    with ZipFile(archive,"r") as zip:
        if install_mode == InstallMode.SERVER:
            try:
                with zip.open(dreams.DirNames.FILE_CONFIG_SERVER) as raw:
                    serverconfig = json.load(raw)
                    install_exclude = serverconfig.get("client-side-only",[])
            except:
                pass

        fl = [f for f in zip.filelist if not any(m for m in install_exclude if f.filename.startswith(m))]

        for index, member in enumerate(fl):
            target_file = f"{install_location}/{member.filename}".replace("\\","/")
            progress = (index+1)/len(fl)
            name = member.filename[member.filename.rfind("/")+1:len(member.filename)]
            dreams.print_progess_bar(
                progress,
                50,
                prepend=f"  installing files: {index+1}/{len(fl)} ["
                )
            
            try:
                zip.extract(member,install_location)
            except:
                pass

    ## CLIENT ONLY ##
    # importing from base profile
    if len(import_list) > 0 and install_mode == InstallMode.CLIENT:
        if verbose: print("  importing from base profile...")
        try:
            import_options(
            install_location,
            import_list=import_list,
            verbose=True
            )
        except RecursionError:
            if verbose: print("  .minecraft not found, ignoring settings import...")

    # pack unpacked, now moving defaults
    if install_defaults:
        if verbose: print("  moving defaults...")
        default_loc_rel = (
                f"{dreams.DirNames.SERVER}/{dreams.DirNames.DEFAULTS}"
            if install_mode == InstallMode.SERVER  
            else (
                dreams.DirNames.DEFAULTS
            )
        )
        default_loc = f"{install_location}/{default_loc_rel}"
        try:
            for root, _, files in os.walk(default_loc):
                for file in files:
                    dest = f"{root.replace(default_loc,install_location)}/{file}".replace("\\","/")
                    rel_path = dest.replace(f"{install_location}/","")
                    if verbose: print(f"    moving {rel_path}...")
                    if not os.path.isfile(dest):
                        shutil.copy(f"{root}/{file}", dest)
        except:
            if verbose: print("  defaults could not be moved!")

    ## SERVER ONLY ##
    # Moving the content of the "world" directory
    # in install/server to the real world directory
    # used by the server.
    if install_mode == InstallMode.SERVER:
        prop_file = dreams.get_as_path("server.properties")
        level_name = None
        if os.path.isfile(prop_file):
            with open(prop_file,"r") as props:
                level_name_key = "level-name="
                for prop in props.readlines():
                    if prop.startswith(level_name_key):
                        level_name = prop.replace(level_name_key,"").strip()
                        break
        if not level_name is None:
            world_dir = dreams.get_as_path(level_name)
            ref_world_dir = dreams.get_as_path(f"{dreams.DirNames.SERVER}/world")
            if os.path.isdir(ref_world_dir) and os.path.isdir(world_dir):
                for root, _, files in os.walk(ref_world_dir):
                    for file in files:
                        src_file = f"{root}/{file}"
                        dest_file = src_file.replace(ref_world_dir,world_dir)
                        if os.path.isfile(dest_file):
                            os.remove(dest_file)
                        if not os.path.isdir(os.path.dirname(dest_file)):
                            os.makedirs(os.path.dirname(dest_file))
                        shutil.copy(src_file,dest_file)
        
        # add a marker file to automatically detect this install as a server install in the future
        marker_file = dreams.get_as_path(dreams.DirNames.FILE_SERVER_MARKER)
        if not os.path.isfile(marker_file):
            if not os.path.isdir(os.path.dirname(marker_file)):
                os.makedirs(os.path.dirname(marker_file))
            with open(marker_file,"w") as mk:
                mk.write("true")


def install_standalone(repo: str, mode: str, install_location:str, import_list=[], verbose=True, archive=None):
    download_tmp = tempfile.TemporaryDirectory()

    if archive is None:
        if verbose: print(f"downloading the modpack from {repo}...")
        archive = download_pack(repo,download_tmp.name)
        if verbose: print("download done!")

    if verbose: print("installing the modpack...")
    install_pack(
        archive,
        install_location.replace("\\","/"),
        import_list=import_list,
        verbose=True,
        install_mode=mode
        )
    if verbose: print("installation done!")

    download_tmp.cleanup()
    if verbose:
        print("cleanup done!")
        if mode == InstallMode.CLIENT:
            print("\n\n\nModpack ready, you may now create a profile in you launcher to use it.")
            print("\nRecommanded RAM: 6G -> -Xmx6G")
            print(f"Profile location: {install_location.replace('/',os.sep)}\n")


def main(args:list):
    mode = InstallMode.CLIENT
    if "--server" in args or "-s" in args:
        mode = InstallMode.SERVER
        print("currently using the server specific install")

    install_dir = dreams.get_root()
    repo = ""

    for a in args:
        if a.startswith("-r=") or a.startswith("--repo="):
            repo = a[a.find("=")+1:len(a)]
            break
    
    imports = []

    if "--import" in args or "-o" in args:
        imports = [
            "options.txt",
            "shaderpacks",
            "resourcepacks"
        ]
    
    mc_dir = dreams.get_minecraft_dir()
    if "--interactive" in args:
        while len(repo) < 1:
            print("\nPlease enter the repository of your modpack :")
            repo = input("repo (URL, or 'x' to abort): ")
            if repo.lower() in ("x", "'x'"):
                print("\nAborting installation...")
                return

        color_install_dir = Color.color(install_dir.replace("\\","/"),Color.CYAN)
        continue_prompt = f"\nThe modpack will be installed in {color_install_dir}"
        
        if mode == InstallMode.CLIENT and len(imports) == 0 and not mc_dir is None:
            print("\nPlease select what to import from your base profile (.minecraft) :")
            if dreams.ask_user(f"  Import {Color.color('settings',Color.from_int(92))} and {Color.color('keybinds',Color.from_int(92))} ?",default_accept=False):
                imports.append("options.txt")
            if dreams.ask_user(f"  Import {Color.color('resource packs',Color.from_int(92))} ?",default_accept=False):
                imports.append("resourcepacks")
            if dreams.ask_user(f"  Import {Color.color('shader packs',Color.from_int(92))} ?",default_accept=False):
                imports.append("shaderpacks")

            if len(imports) > 0:
                continue_prompt += f"\nwith these imports from {Color.color(mc_dir,Color.CYAN)} :"
                for i in imports:
                    continue_prompt += f"\n  {i}"
        continue_prompt += "\n\nAccept and continue with the installation ?"
        if not dreams.ask_user(continue_prompt):
            print("\nAborting installation...")
            return

    if len(repo) < 1:
        print("Repository not provided, aborting installation.")
        return
    
    parsed = urlparse(repo)
    if len(parsed.scheme) < 1 and not "/" in repo:
        # allowing a shortcut to my own general
        # repository if only the name is provided
        repo = f"{DEFAULT_REPOSITORY_PATH}/{repo}"

    install_standalone(
        repo,
        mode,
        install_dir,
        import_list=imports,
        verbose=True
        )

if __name__ == "__main__":
    main(os.sys.argv)
