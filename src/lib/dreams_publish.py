#!/usr/bin/env python3
import os
import json
import lib.dreams as dreams

def main(args:list):
    import pysftp
    import paramiko
    from stat import S_ISDIR
    
    rel_dir = dreams.get_as_path(dreams.DirNames.RELEASES).replace("\\","/")
    manifest = dreams.get_manifest()
    latest = sorted(os.listdir(rel_dir),reverse=True)[0]
    latest_path = f"{rel_dir}/{latest}".replace("\\","/")

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
    remote_root = "$HOME/webserver/modpacks"
    remote_pack_root = f"{remote_root}/{modpack_name}"
    remote_release_dir = f"{remote_pack_root}/{dreams.DirNames.Server.VERSIONS}"

    release_bundle_command = f"cd {remote_root} && python3 update_release.py {modpack_name}"

    
    ssh_client = paramiko.SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_key_file = f"{os.path.expanduser('~')}/.ssh/id_rsa"

    ssh_password = None
    ssh_key = None

    try:
        ssh_key = paramiko.RSAKey.from_private_key_file(ssh_key_file)
    except paramiko.PasswordRequiredException as e:
        psswd = input(f"Please input the password for your ssh private key : ").strip()
        ssh_key = paramiko.RSAKey.from_private_key_file(ssh_key_file,password=psswd)
    except (IOError, paramiko.SSHException):
        print("SSH privatekey loading failed, attempting to use password login instead...")
        ssh_password = input(f"SSH login password (u:{user}) : ").strip()

    ssh_client.connect(
        server,
        username=user,
        password=ssh_password,
        pkey=ssh_key
    )
        
    with ssh_client.open_sftp() as sftp:
        def is_dir(remote_path:str) -> bool:
            try:
                return S_ISDIR(sftp.stat(remote_path).st_mode)
            except IOError:
                return False
        def rm_rec(remote_path:str):
            if not is_dir(remote_path):
                sftp.remove(remote_path)
            else:
                for f in sftp.listdir(remote_path):
                    rm_rec(f"{remote_path}/{f}")
                sftp.rmdir(remote_path)

        latest_dir = f"{remote_release_dir}/{latest}"

        if latest in sftp.listdir(remote_release_dir):
            print("removing the old release...")
            rm_rec(latest_dir)
        
        print("sending the new one...")
        if not latest in sftp.listdir(remote_release_dir):
            sftp.mkdir(latest)
        #
        # OLD
        #
        transfer_queue = dict()
        print("listing local files...")
        for root,_,files in os.walk(latest_path):
            for f in files:
                full_path = f"{root}/{f}".replace("\\","/")
                parent = os.path.dirname(full_path).replace("\\","/")
                rel_path = full_path.replace(f"{latest_path}/","")
                rel_parent = parent.replace(f"{latest_path}/","") if not parent == latest_path else ""
                rem_parent_path = f"{latest_dir}/{rel_parent}"
                rem_file_path = f"{latest_dir}/{rel_path}"
                if not is_dir(rem_parent_path):
                    sftp.mkdir(rem_parent_path)
                transfer_queue[full_path] = rem_file_path
        print("local files discovered!")
        print("sending to remote...")
        for index,data in enumerate(transfer_queue.items()):
            dreams.print_progess_bar(
                (index+1)/len(transfer_queue),
                50,
                f"transfering files : ({index+1}/{len(transfer_queue)}) ["
            )
            sftp.put(
                localpath=data[0],
                remotepath=data[1],
                confirm=True
            )
        print("all files sent to remote, executing release script on remote...")

    _, stdout, _ = ssh_client.exec_command(release_bundle_command)  # Non-blocking call
    stdout.channel.set_combine_stderr(True)
    exit_status = stdout.channel.recv_exit_status()          # Blocking call
    if exit_status == 0:
        print ("release successfully sent and bundled!")
    else:
        print("release was sent, but could not be bundled. ", exit_status)
    ssh_client.close()

if __name__ == "__main__":
    main(os.sys.argv[1:])
