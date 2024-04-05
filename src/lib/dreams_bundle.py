#!/bin/env python3
import os
import tempfile
import shutil
import lib.dreams as dreams
from zipfile import ZipFile, ZIP_DEFLATED
import zipfile
from lib.dreams import DirNames
from lib.dreams_upgrade import ContentDifference
from os import sep as SEP
import json

def get_orphan_configs() -> None:
    
    root = dreams.get_root()
    orphans = []
    config_matches = dreams.get_config().get("config-matches",{})

    modlist = [file for file in os.listdir(f"{root}/{DirNames.MODS}") if file.endswith(".jar")]

    for file in os.listdir(f"{root}/{DirNames.CONFIG}"):
        name = config_matches.get(file,None)
        if name is None:
            name = ""
            for l in file[0:file.rfind(".")] if "." in file else file:
                if not l.isalnum():
                    break
                name += l
        if not any(name.lower() in mod.lower().replace("-","").replace("_","") for mod in modlist):
            orphans.append(file)
    return orphans

def get_version_adjustement(current_version:str, diff:ContentDifference) -> str:
    split = current_version.split(".")
    version = []
    for v in range(max(len(split),3)):
        sub = split[v] if len(split) > v else "0"
        version.append(sub)
    # so now we are sure that version has at least 3 elements in it:
    # generation (0) -> major (1) -> patch (2)
    major = int(version[1])
    patch = int(version[2])

    if (
        (len(diff.added) > 0 
        or len(diff.removed) > 0)
        ):
        combi = [*diff.added, *diff.removed]
        if any(f for f in combi if f.startswith(dreams.DirNames.MODS)):
            major += 1
            patch = 0
        else:
            patch += 1
    elif len(diff.modified) > 0:
        patch += 1

    ver_string = f"{version[0]}.{major}"
    if patch > 0:
        ver_string += f".{patch}"

    return ver_string

def get_file_content_format(relative_filepath:str, root:str) -> str:
    absolute = f"{root}/{relative_filepath}"
    return f"{relative_filepath}:{dreams.get_file_hash(absolute)}"

def split_file_hash(entry:str) -> (str,str):
    if ":" in entry:
        split = entry.split(":")
        return(split[0],split[1])
    return entry

def exclude_from_diff(
        relative:str, 
        diff:ContentDifference,
        exclude_added=True,
        exclude_removed=True,
        exclude_modified=True
        ):
    if exclude_added and relative in diff.added:
        diff.added.remove(relative)
    if exclude_removed and relative in diff.removed:
        diff.removed.remove(relative)
    if exclude_modified and relative in diff.modified:
        diff.modified.remove(relative)

def main(args:list):
    archive_result = "--archive" in args or "-a" in args
    if "--orphans" in args or "-o" in args:
        o_config = get_orphan_configs()
        if len(o_config) > 0:
            print("Orphan configs:")
            for c in o_config:
                print(f"  {c if '.' in c else f'{c}/'}")
        else:
            print("No orphan configs!")
        return
    
    manifest = dreams.get_manifest()
    root = dreams.get_root()

    # bundling the modpack
    print("→ bundling the modpack...")
    include = []
    exclude = []

    content_config = dreams.get_config()
    include = content_config.get("bundle-include",[])
    exclude = content_config.get("bundle-exclude",[])

    if content_config.get("bundle-exclude-orphans", False):
        # auto exclude orphan configs
        print("  excluding orphans...")
        for config in get_orphan_configs():
            exclude.append(f"config/{config}")

    # checking the difference between the last bundled version
    # and the current
    version = manifest['version']
    target_version = version
    should_upgrade = "--increment" in args or "-i" in args
    interactive = "--interactive" in args
    release_dir = dreams.get_as_path(DirNames.RELEASES)
    first_release = not os.path.isdir(release_dir) or len(os.listdir(release_dir)) == 0
    if not os.path.isdir(release_dir):
        os.mkdir(release_dir)
    if not first_release and (should_upgrade or interactive):
        print("  calculating version difference for auto increment...")
        last_version = sorted(os.listdir(release_dir),reverse=True)[0]
        if not last_version[last_version.rfind("-")+1:len(last_version)] == version:
            print("  version increment explicitly specified, skipping.")
        else:
            diff = ContentDifference(
                ContentDifference.get_content(f"{dreams.get_as_path(DirNames.RELEASES)}/{last_version}"),
                ContentDifference.get_content(root, use_cache=False, include=include, exclude=exclude)
                )
            exclude_from_diff(DirNames.FILE_VERSION_CONTENT, diff)
            exclude_from_diff(DirNames.FILE_VERSION_CHECKER, diff)
            adj_version = get_version_adjustement(manifest["version"], diff)
            skip = adj_version == version
            if not skip and interactive and not should_upgrade:
                answer = dreams.ask_user(
f"""  Version difference detected:
    current: {version}
    suggested: {adj_version}
    patchnote:
{diff.patchnote(fancy=False,indent=8)}
  Would you like to automatically increment the version from {version} to {adj_version} ?""")
                should_upgrade = answer
            if skip:
                print("  no version difference found, ignoring auto increment.")
            if should_upgrade:
                print(f"  auto incrementing from {version} to {adj_version}")
                target_version = adj_version

    if not version == target_version:

        print("  incrementing version...")

        version = target_version
        man_file = dreams.get_as_path(DirNames.FILE_MANIFEST)
        data = {}
        with open(man_file,"r") as out:
            data = json.load(out)
            data["version"] = version
        with open(man_file,"w") as out:
            json.dump(data,out,indent=4)

        print("✓ incrementation done!")

    version_config_str = f"""
#General settings
[general]
	#The CurseForge project ID for the modpack
	#Range: > 0
	modpackProjectID = 0
	#The name of the modpack
	modpackName = "{manifest.get('name', '?')}"
	#The version of the modpack
	modpackVersion = "{version}"
	#Use the metadata.json to determine the modpack version
	#ONLY ENABLE THIS IF YOU KNOW WHAT YOU ARE DOING
	useMetadata = false


"""
    
    vrs_path = dreams.get_as_path(dreams.DirNames.FILE_VERSION_CHECKER)
    if not os.path.isdir(os.path.dirname(vrs_path)):
        os.makedirs(os.path.dirname(vrs_path))
    with open(vrs_path,"w") as out:
        out.write(version_config_str)
    
    bundle_list = dreams.list_content(root, include=include, exclude=exclude)

    release_dir = f"{root}/{DirNames.RELEASES}"

    dir_name = f"{version}"
    dir_path = f"{release_dir}/{dir_name}".replace("\\","/")

    if os.path.isdir(dir_path):
        shutil.rmtree(dir_path)

    if not os.path.isdir(release_dir):
        os.makedirs(release_dir)

    for index, file in enumerate(bundle_list):
        absolute = f"{root}{SEP}{file}"
        dreams.print_progess_bar(
                (index+1)/len(bundle_list),
                50,
                prepend=f"  bundling files: {index+1}/{len(bundle_list)} ["
                )
        if not dreams.is_excluded(file,exclude):
            dest_path = f"{dir_path}/{file}"
            if not os.path.isdir(os.path.dirname(dest_path)):
                os.makedirs(os.path.dirname(dest_path))
            shutil.copy(absolute,dest_path)
        else:
            continue

    print("✓ bundling done!")

    sep = os.sep

    print("  creating version content file...")

    content_str = ""
    content_queue = []
    for root, _, files in os.walk(dir_path):
        for file in files:
            relative = f"{root}/{file}".replace("\\","/").replace(f"{dir_path}/","")
            content_queue.append(relative)

    for index, key in enumerate(content_queue):
        dreams.print_progess_bar(
            (index+1)/len(content_queue),
            50,
            f"  hashing files: {(index+1)}/{len(content_queue)} ["
        )
        content_str += (get_file_content_format(key, dir_path)+"\n")
    content_str += DirNames.FILE_VERSION_CONTENT

    content_path = f"{dir_path}/{DirNames.FILE_VERSION_CONTENT}"
    if not os.path.isdir(os.path.dirname(content_path)):
        os.makedirs(os.path.dirname(content_path))
    with open(content_path, "w") as out:
        out.write(content_str)

    print("✓ content file written!")

    if archive_result:

        print("  creating the archive...")
        
        zip_file_path = f"{release_dir}/{dir_name}.zip"
        shutil.make_archive(zip_file_path, 'zip', dir_name)

        print("  cleaning up...")

        shutil.rmtree(dir_path)

        print("✓ archive created!")
    
    print(f"\n\n\nBundling completed successfuly! The modpack is available at \n{release_dir}{sep}{dir_name}\n".replace("/",sep))

if __name__ == "__main__":
    main(os.sys.argv)
