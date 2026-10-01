# SPDX-License-Identifier: Apache-2.0
"""Build native kernel and retain explicit local compiler/source identities."""
import argparse
import hashlib
import json
import platform
import shlex
import shutil
import subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',default='c++')
    parser.add_argument('--flags',default='-std=c++20 -O2 -Wall -Wextra -Wpedantic -Werror')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    target=root/'build/quantfabric'
    target.parent.mkdir(exist_ok=True)
    command=shlex.split(args.compiler)+shlex.split(args.flags)+['core/main.cpp','-o','build/quantfabric']
    subprocess.run(command,cwd=root,check=True)
    version=subprocess.run(shlex.split(args.compiler)+['--version'],capture_output=True,text=True,check=True).stdout
    metadata={'command':command,'compiler_path':shutil.which(command[0]),'compiler_version':version,
              'platform':platform.platform(),'machine':platform.machine(),
              'source_sha256':hashlib.sha256((root/'core/main.cpp').read_bytes()).hexdigest(),
              'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
              'trust':'local build record, not authenticated provenance'}
    (root/'build/metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')


if __name__=='__main__':
    main()
