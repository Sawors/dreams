#!/usr/bin/env bash
entry_point="$PWD/install/src/__main__.py"
/usr/bin/env python3 "$entry_point" --mode=bundle --interactive --no-hold && /usr/bin/env python3 "$entry_point" --mode=publish --interactive --no-hold
