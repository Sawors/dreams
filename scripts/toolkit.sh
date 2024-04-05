#!/usr/bin/env bash

repo=https://github.com/Sawors/dreams/archive/refs/heads/master.zip
download_dir=$(mktemp -d)
src_dir=${PWD}/install
entry_point=__main__.py
entry_point_path=${src_dir}/src/${entry_point}
toolkit_args=--interactive

# not using embedded python on Linux

if test -f "${entry_point_path}";
then
    echo Upgrading toolkit...
else
    echo Installing toolkit...
fi

curl -LJ "$repo" -o "$download_dir/toolkit.zip"
unzip -qq "$download_dir/toolkit.zip" -d "$download_dir"
mkdir -p "$src_dir"
rm -r "${src_dir}/src"
mv "${download_dir}/dreams-master/src" "$src_dir"
mv ${download_dir}/dreams-master/scripts/* "$PWD/"
rm -r "$download_dir"

if test -f "${entry_point_path}";
then
    echo Toolkit successfully installed !

    if ! /usr/bin/env python3 --version 2>&1 > /dev/null;
    then
        rm -r "${src_dir}/src"
        echo Python not found, aborting.
        exit 9009
    fi
    echo Automatically starting its execution...
    /usr/bin/env python3 "$entry_point_path" $toolkit_args $@
else
    echo Download failed, aborting.
    exit 1
fi
