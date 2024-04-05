
import os
import shutil
import tempfile
from urllib.parse import urlparse
import lib.dreams as dreams
import lib.dreams_install as dreams_install
from lib.dreams_install import InstallMode
from http.client import HTTPSConnection
from zipfile import ZipFile
from datetime import datetime
import json
import copy
import urllib

def get_version_content(lines:list) -> dict:
    content = dict()
    for l in lines:
        stripped = l.decode("UTF-8").strip().replace("\\","/")
        if ":" in stripped:
            split = stripped.split(":")
            content[split[0]] = split[1]
        else:
            content[stripped] = ""
    return content

class ContentDifference:
    added: list
    removed: list
    modified: list
    old_version = None
    new_version = None

    def __init__(self, added:list, removed:list, modified:list, old_version:str, new_version:str):
        self.added = added
        self.removed = removed
        self.modified = modified
        self.old_version = old_version
        self.new_version = new_version

    def get_content(path:str, use_cache=True, include=[], exclude=[], config=None) -> dict:
        if os.path.isdir(path):
            content_list_file = dreams.get_as_path(dreams.DirNames.FILE_VERSION_CONTENT,root=path)
            if use_cache and os.path.isfile(content_list_file):
                with open(content_list_file,"rb") as file:
                    vc = get_version_content(file.readlines())
                    for f in set(vc.keys()):
                        if not os.path.isfile(f"{path}/{f}"):
                            del vc[f]
                    return vc
            else:
                content = dict()
                if config is None:
                    config = dreams.get_config(root=path)
                for c in dreams.list_content(
                    path,
                    include=include if len(include) > 0 else config.get("bundle-include",["/"]),
                    exclude=exclude if len(exclude) > 0 else config.get("bundle-exclude",[])
                    ):
                    content[c] = dreams.get_file_hash(f"{dreams.get_as_path(c)}")
                return content
            
        elif os.path.isfile(path) and path.endswith(".zip"):
            with ZipFile(path) as zipf:
                with zipf.open(dreams.DirNames.FILE_VERSION_CONTENT,"r") as file:
                    return get_version_content(file.readlines())
        raise FileNotFoundError("found nowhere to search for content")

    def __init__(self, old_content:dict, new_content:dict):

        removed = [o for o in old_content.keys() if not o in new_content.keys()]
        added = [o for o in new_content.keys() if not o in old_content.keys()]
        modified = [k for k,v in new_content.items() if k in old_content.keys() and not old_content[k] == v]

        self.added = added
        self.removed = removed
        self.modified = modified
    
    def from_path(self, old_path:str, new_path:str, config=dreams.get_config()):
        old_version = None
        new_version = None

        old_content = self.get_content(old_path, config)
        try:
            manifest = dreams.get_manifest(root=old_path)
            old_version = manifest.get("version",old_version)
        except:
            pass
        
        new_content = self.get_content(new_path, config)
        if os.path.isdir(new_path):
            try:
                manifest = dreams.get_manifest(root=new_path)
                new_version = manifest.get("version", new_version)
            except:
                pass
        else:
            with ZipFile(new_path) as zipf:
                try:
                    with zipf.open(dreams.DirNames.FILE_MANIFEST,"r") as manifest:
                        manifest = json.load(manifest)
                        new_version = manifest.get("version", new_version)
                except:
                    pass
                
        diff = ContentDifference(old_content, new_content)
        if not old_version is None:
            diff.old_version = old_version
        if not new_version is None:
            diff.new_version = new_version
        return diff

    def patchnote(self,fancy=True,indent=0) -> str:
        patch_str = ""
        patch_title = f"[PATCHNOTE {self.old_version} -> {self.new_version}]"
        add_symbol = "[+]"
        remove_symbol = "[-]"
        modify_symbol = "[~]"
        title_sep_length = 20
        line = "-"
        indent_chars = indent*" "
        title_full_line = f"{line*title_sep_length} {patch_title} {line*title_sep_length}"
        def as_line(line:str) -> str:
            return indent_chars+line.replace("\n","")+"\n"

        if fancy:
            patch_str += as_line((len(title_full_line)*line))
            patch_str += as_line(title_full_line)
            patch_str += as_line((len(title_full_line)*line)+"\n")
        if len(self.added) > 0:
            if not fancy:
                patch_str += as_line("Added :")
            for f in self.added:
                patch_str += as_line(f"{add_symbol} {f}")
            patch_str += as_line("")
        if len(self.removed) > 0:
            if fancy:
                patch_str += as_line((len(title_full_line)*line))
                patch_str += as_line("")
            else:
                patch_str += as_line("Removed :")
            for f in self.removed:
                patch_str += as_line(f"{remove_symbol} {f}")
            patch_str += as_line("")
        if len(self.modified) > 0:
            if fancy:
                patch_str += as_line((len(title_full_line)*line))
                patch_str += as_line("")
            else:
                patch_str += as_line("Modified :")
            for f in self.modified:
                patch_str += as_line(f"{modify_symbol} {f}")
        if fancy:
            patch_str += as_line((len(title_full_line)*line))

        return patch_str  

def compute_difference(server_domain:str, reference_install:str, target_version:str, config:dict) -> ContentDifference:
    parsed = urlparse(server_domain)
    
    old_content = ContentDifference.get_content(reference_install,config)
    new_content = {}
    connection = HTTPSConnection(parsed.netloc, timeout=10)
    # first, get the latest version
    
    if not target_version is None:
        version_content_file = f"{target_version}/{dreams.DirNames.FILE_VERSION_CONTENT}"
    else:
        return None
    connection.request("GET",f"{parsed.path}{dreams.ServerLocation.VERSIONS}/{version_content_file}")
    with connection.getresponse() as response:
        if not response.status == 200:
            return None
        new_content = get_version_content(response.readlines())
    if len(new_content) == 0:
        return None
    
    connection.close()
    return ContentDifference(old_content, new_content)

def download_upgrade(
        server_domain:str, 
        download_location:str, 
        target_version:str, 
        diff:ContentDifference,
        verbose=True
    ):
    parsed = urlparse(server_domain)
    _chunk_size = 65536
    if os.path.isfile(download_location):
        raise FileExistsError("file already exists")
    if not os.path.isdir(download_location):
        raise FileNotFoundError("download loaction does not exist")

    connection = HTTPSConnection(parsed.netloc, timeout=180)
    # downloading files in diff.added and diff.modified
    download_queue = diff.added + diff.modified
    queue_length = len(download_queue)
    try:
        for index, f in enumerate(download_queue):
            connection.request("GET",urllib.parse.quote(f"{parsed.path}{dreams.ServerLocation.VERSIONS}/{target_version}/{f}"))
            dl_target = f"{download_location}/{f}"
            if not os.path.isdir(os.path.dirname(dl_target)):
                os.makedirs(os.path.dirname(dl_target))
            if verbose:
                dreams.print_progess_bar(
                    (index+1)/queue_length,
                    50,
                    prepend=f"  downloading upgrade patch: ["
                    )
            with connection.getresponse() as response:
                with open(dl_target, "ab") as data_output:
                    while chunk := response.read(_chunk_size):
                        data_output.write(chunk)
    except RuntimeError as e:
        print(f"error dl: {e}")
        return None
    
    connection.close()

def install_upgrade(
        source:str, 
        install_location:str, 
        difference:ContentDifference, 
        install_defaults=True, 
        verbose=True, 
        install_mode=InstallMode.CLIENT,
        config=dreams.get_config()
    ) -> ContentDifference:
    # "source" is the new version, "install location" points to where
    # the old one is installed.
    if not os.path.isdir(source):
        raise FileNotFoundError("source is not a directory")
    if not os.path.isdir(install_location):
        raise NotADirectoryError("install location is not a directory")
    
    result_diff = copy.deepcopy(difference)

    ignore_global = config.get("upgrade-ignore-global",[])
    ignore_remove = config.get("upgrade-ignore-remove",[])
    ignore_add = config.get("upgrade-ignore-add",[])
    ignore_modify = config.get("upgrade-ignore-modify",[])

    # adding added
    for index, a in enumerate(difference.added):
        if any(s for s in ignore_add if a.startswith(s)) or a in ignore_global:
            result_diff.added.remove(a)
            continue
        dreams.print_progess_bar(
            (index+1)/len(difference.added),
            50,
            prepend=f"  adding files: {index+1}/{len(difference.added)} ["
        )

        src = f"{source}/{a}"
        target = f"{install_location}/{a}"
        if not os.path.isdir(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))
        if not os.path.isfile(target):
            shutil.copy(src,target)
        else:
            print(f"warning: file {a} already exists")

    # removing removed
    for index, r in enumerate(difference.removed) or r in ignore_global:
        if any(s for s in ignore_remove if r.startswith(s)):
            result_diff.removed.remove(r)
            continue
        target = f"{install_location}/{r}"
        if os.path.isfile(target):
            dreams.print_progess_bar(
                (index+1)/len(difference.removed),
                50,
                prepend=f"  removing files: {index+1}/{len(difference.removed)} ["
                )

            os.remove(target)
        else:
            print(f"warning: file {r} has already been removed")

    # replacing modified
    for index, m in enumerate(difference.modified) or m in ignore_global:
        if any(s for s in ignore_modify if m.startswith(s)):
            result_diff.modified.remove(m)
            continue
        if verbose: dreams.print_progess_bar(
            (index+1)/len(difference.modified),
            50,
            prepend=f"  replacing files: {index+1}/{len(difference.modified)} ["
            )
        
        src = f"{source}/{m}"
        target = f"{install_location}/{m}"
        if not os.path.isdir(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))

        try:
            with open(src,"r") as input:
                with open(target,"w") as output:
                    output.write(input.read())
        except:
            pass

    if install_defaults:
        if verbose: print("  moving defaults...")
        default_loc_rel = dreams.DirNames.DEFAULTS
        default_loc = f"{install_location}/{default_loc_rel}"
        try:
            for root, _, files in os.walk(default_loc):
                for file in files:
                    dest = f"{root.replace(default_loc,install_location)}/{file}".replace("\\","/")
                    rel_path = dest.replace(f"{install_location}/","")
                    if not os.path.isfile(dest): 
                        if verbose: print(f"    moving {rel_path}...")
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
                        dest_file = src_file.replace(ref_world_dir, world_dir)
                        rel_file = src_file.replace("\\","/").replace(f"{root}/","")
                        if os.path.isfile(dest_file):
                            result_diff.modified.append(rel_file)
                            os.remove(dest_file)
                        else:
                            result_diff.added.append(rel_file)
                        if not os.path.isdir(os.path.dirname(dest_file)):
                            os.makedirs(os.path.dirname(dest_file))
                        shutil.copy(src_file,dest_file)

    return result_diff

def upgrade_pack(install_mode: str, install_location:str, repository:str, verbose=True, generate_patchnote=True, wait_for_confirm=False):
    download_tmp = tempfile.TemporaryDirectory()
    latest = dreams_install.get_latest_release_name(repository)

    is_local = dreams.get_current_config_type().is_local
    config_remote_root = f"{repository}/{dreams.ServerLocation.VERSIONS}/{latest[1]}"
    config = dreams.get_config(
        type=dreams.ConfigType(True,is_local),
        remote_root=config_remote_root
    )
    # Aggregating client and server configs if
    # install_mode is server. Every entry
    # defined in the server config will
    # COMPLETELY OVERRIDE the one in client config.
    if install_mode == InstallMode.SERVER:
        serverconfig = dreams.get_config(
            type=dreams.ConfigType(False,is_local),
            remote_root=config_remote_root
        )
        for k, v in serverconfig.items():
            config[k] = v

    if verbose: 
        print(f"latest release is {latest[1]}")
        print(f"determinating patch content...")
    diff = compute_difference(repository, install_location, latest[1], config=config)

    if wait_for_confirm:
        print(f"\nThe modpack will be upgraded from {dreams.get_manifest().get('version','?')} to {latest[0]}.")
        print(f"Patchnote :\n{diff.patchnote(fancy=False,indent=2)}")
        if not dreams.ask_user("\nShould the update proceed and apply the changes listed above ?"):
            print("Aborting the upgrade process.")
            return

    # adding to modified will add it to the old install even if it does not exist
    if not dreams.DirNames.FILE_VERSION_CONTENT in diff.modified:
        diff.modified.append(dreams.DirNames.FILE_VERSION_CONTENT)
    if dreams.DirNames.FILE_VERSION_CONTENT in diff.added:
        diff.added.remove(dreams.DirNames.FILE_VERSION_CONTENT)
    if not dreams.DirNames.FILE_VERSION_CHECKER in diff.modified:
        diff.modified.append(dreams.DirNames.FILE_VERSION_CHECKER)
    if dreams.DirNames.FILE_VERSION_CHECKER in diff.added:
        diff.added.remove(dreams.DirNames.FILE_VERSION_CHECKER)
    diff.new_version = latest[0]
    download_loc = download_tmp.name
    if verbose: print("downloading the modpack...")
    download_upgrade(repository, download_loc, latest[1], diff)
    if verbose: print("download done!")

    if verbose: print("upgrading the modpack...")
    try:
        old_manifest = dreams.get_manifest()
        diff.old_version = old_manifest.get("version","?")
    except:
        diff.old_version = "?"

    result_diff = install_upgrade(download_loc, install_location, diff, install_mode=install_mode, config=config)

    if generate_patchnote:
        patch_str = f"{datetime.now().isoformat()}\n\n{result_diff.patchnote()}"
        patch_file_name = f"patchnote_{result_diff.old_version}-{result_diff.new_version}.log"
        patch_target = f"{dreams.get_as_path(dreams.DirNames.PATCHNOTES)}/{patch_file_name}"
        if not os.path.isdir(os.path.dirname(patch_target)):
            os.makedirs(os.path.dirname(patch_target))
        with open(patch_target,"w") as wrt:
            wrt.write(patch_str)
    if verbose: print("upgrade done!")

    download_tmp.cleanup()
    if verbose: 
        print("cleanup done!")
        print(f"\n\n\nModpack upgraded from version {diff.old_version} to {diff.new_version}!")

def is_standalone() -> bool:
    try:
        dreams.get_manifest()
    except:
        return True
    root = dreams.get_root()
    return len([f for f in os.listdir(root) if os.path.isdir(f"{root}/{f}")]) == 0

def main(args:list):
    install_mode = InstallMode.CLIENT
    if "--server" in args or "-s" in args:
        install_mode = InstallMode.SERVER
        print("currently using the server specific install")
    
    # backup if an upgrade has been started in an empty directory
    if is_standalone():
        print("the modpack does not seem to be already installed, defaulting to \'install\' mode...")
        #dreams_install.main(args)
        return
    #
    # upgrade mode
    #
    # We consider that the modpack is already installed.
    
    repository_url = dreams.get_config_option("repository", "")
    if len(repository_url) < 1:
        print("No repository has been found in the config, aborting upgrade.")
        return
    interactive = "--interactive" in args
    upgrade_pack(install_mode,dreams.get_root(),repository_url,wait_for_confirm=interactive)

if __name__ == "__main__":
    main(os.sys.argv)
