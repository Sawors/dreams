#!/usr/bin/env python3
import os
import json
import pysftp
import paramiko
import lib.dreams as dreams

def main(args:list):
    rel_dir = dreams.get_as_path(dreams.DirNames.RELEASES).replace("\\","/")
    manifest = dreams.get_manifest()
    latest = sorted(os.listdir(rel_dir),reverse=True)[0]
    latest_path = f"{rel_dir}/{latest}".replace("\\","/")

    psswd = args[len(args)-1] if len(args) > 0 else None

    config_publish_file = dreams.get_as_path(dreams.DirNames.FILE_CONFIG_PUBLICATION).replace("\\","/")
    if not os.path.isfile(config_publish_file):
        print("Publication config not found, aborting.")
        return
    config_publish = {}
    try:
        with open(config_publish_file,"r",encoding="UTF-8") as infile:
            config_publish = json.load(infile)
    except Exception:
        print("Could not load the publication config, aborting.")
        return

    server = config_publish.get("server","")
    user = config_publish.get("user","")
    token = config_publish.get("token","")

    if len(server) == 0 or len(user) == 0:
        print("Please provide a server and a user in the publication config.")
        return

    modpack_name = manifest['name']
    remote_release_dir = f"webserver/modpacks/{modpack_name}/versions"

    release_bundle_command = f"cd $HOME/webserver/modpacks && python3 update_release.py {modpack_name}"

    if psswd is None:
        psswd = input(f"Password to the ftp server (u:{user}) : ").strip()


    with pysftp.Connection(server, username=user, password=psswd) as sftp:
        with sftp.cd(remotepath=remote_release_dir):
            if latest in sftp.listdir("./"):
                print("removing the old release...")
                sftp.execute(f"cd $HOME/{remote_release_dir} && rm -R {latest}")
            print("sending the new one...")
            if not latest in sftp.listdir("./"):
                sftp.mkdir(latest)

            transfer_queue = dict()
            print("listing local files...")
            for root,_,files in os.walk(latest_path):
                for f in files:
                    full_path = f"{root}/{f}".replace("\\","/")
                    parent = os.path.dirname(full_path).replace("\\","/")
                    rel_path = full_path.replace(f"{latest_path}/","")
                    rel_parent = parent.replace(f"{latest_path}/","") if not parent == latest_path else ""
                    rem_parent_path = f"{sftp.pwd}/{latest}/{rel_parent}"
                    rem_file_path = f"{sftp.pwd}/{latest}/{rel_path}"
                    if not sftp.isdir(rem_parent_path):
                        sftp.makedirs(rem_parent_path)
                    transfer_queue[full_path] = rem_file_path
            print("local files discovered!")
            print("sending to remote...")
            for index,data in enumerate(transfer_queue.items()):
                dreams.print_progess_bar(
                    (index+1)/len(transfer_queue),
                    50,
                    f"transfering files : ({index+1}/{len(transfer_queue)}) ["
                )
                sftp.put(data[0],data[1])
            print("all files sent to remote, executing release script on remote...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(server,username=user,password=psswd)
    _, stdout, _ = ssh.exec_command(release_bundle_command)  # Non-blocking call
    stdout.channel.set_combine_stderr(True)
    exit_status = stdout.channel.recv_exit_status()          # Blocking call
    if exit_status == 0:
        print ("release successfully sent and bundled!")
    else:
        print("release was sent, but could not be bundled. ", exit_status)
    ssh.close()

if __name__ == "__main__":
    main(os.sys.argv[1:])
