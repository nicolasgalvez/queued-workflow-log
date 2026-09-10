"""Write each queued workflow to <user dir>/queued/<datetime>-<hash>.json.

Named by wall-clock time (millisecond resolution) plus a short random suffix,
e.g. 20260909-212733-481-d3f07a.json. Never the queue number: it restarts at
0 on every ComfyUI restart, so 1.json, 2.json... collide and say nothing
about which run they came from.

Headless: this pack contributes no nodes and no UI. Its entire effect is this
module's import, per the documented custom-node lifecycle
(https://docs.comfy.org/custom-nodes/backend/lifecycle). Errors are not
swallowed: ComfyUI core catches on_prompt handler failures, logs the
traceback, and the queue proceeds.

NOTE: PromptServer.add_on_prompt_handler is NOT documented on docs.comfy.org.
It is a long-standing hook in ComfyUI core (server.py: defined at
add_on_prompt_handler, invoked from trigger_on_prompt at the top of the
POST /prompt route). The docs describe no supported alternative for observing
queue submission server-side.
"""

import json
import os
import secrets
from datetime import datetime

import folder_paths
from server import PromptServer

QUEUED_DIR = os.path.join(folder_paths.get_user_directory(), "queued")


def _save_queued_workflow(json_data):
    workflow = (json_data.get("extra_data") or {}).get("extra_pnginfo", {}).get("workflow")
    if workflow is not None:
        now = datetime.now()
        name = f"{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}-{secrets.token_hex(3)}"
        os.makedirs(QUEUED_DIR, exist_ok=True)
        # "x" never truncates an existing log; a collision raises, core logs it.
        path = os.path.join(QUEUED_DIR, f"{name}.json")
        with open(path, "x", encoding="utf-8") as f:
            json.dump(workflow, f)
    return json_data


PromptServer.instance.add_on_prompt_handler(_save_queued_workflow)

# This pack contributes no nodes. The empty mapping is what makes ComfyUI treat
# the module as a loaded custom-node package rather than skipping it.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
