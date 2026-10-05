"""Write the files the model server reads to start, as a JSON array, to argv[1].

Run inside the llm-d-cuda image: imports what the server imports on its way
to loading a model (torch, vLLM, its OpenAI API server) and lists every module
file and every mapped shared object of the process, resolved to the path the
image stores. A GPU-less runner gets as far as the imports; the CUDA libraries
torch links are mapped by then. The list is the prefetch set the lazily pulled
variants carry, so a node fetches these spans first.
"""

import importlib
import json
import os
import sys

for name in ("torch", "vllm", "vllm.entrypoints.openai.api_server"):
    try:
        importlib.import_module(name)
    except Exception as err:  # noqa: BLE001 - a GPU-less import may stop early; what loaded counts
        print(f"import {name}: {err}", file=sys.stderr)

files = set()
for module in list(sys.modules.values()):
    path = getattr(module, "__file__", None)
    if path:
        files.add(os.path.realpath(path))
with open("/proc/self/maps") as maps:
    for line in maps:
        fields = line.split()
        if len(fields) >= 6 and fields[5].startswith("/"):
            files.add(os.path.realpath(fields[5]))
files.add(os.path.realpath(sys.executable))

startup = sorted(f for f in files if os.path.isfile(f))
with open(sys.argv[1], "w") as out:
    json.dump(startup, out, indent=0)
print(f"{len(startup)} start-up files", file=sys.stderr)
