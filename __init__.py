"""Write each queued workflow to <user dir>/queued/<name>.json.

The file is named by the client-supplied prompt_id when the POST /prompt body
carries one (ComfyUI's own frontend does this, and so do clients like
workprint-studio) — so the filename is the Job ID shown in the UI. A body
without a prompt_id falls back to the job number (<number>.json), matching
how the /prompt route names the job just after this handler runs.

Headless: this pack contributes no nodes and no UI. Its entire effect is this
module's import, per the documented custom-node lifecycle
(https://docs.comfy.org/custom-nodes/backend/lifecycle).

NOTE: PromptServer.add_on_prompt_handler is NOT documented on docs.comfy.org.
It is a long-standing hook in ComfyUI core (server.py: defined at
add_on_prompt_handler, invoked from trigger_on_prompt at the top of the
POST /prompt route). The docs describe no supported alternative for observing
queue submission server-side.
"""

import json
import os
import time

import folder_paths
from server import PromptServer

QUEUED_DIR = os.path.join(folder_paths.get_user_directory(), "queued")


def _save_queued_workflow(json_data):
    try:
        workflow = (json_data.get("extra_data") or {}).get("extra_pnginfo", {}).get("workflow")
        if workflow is not None:
            # Name by the client-supplied prompt_id when present (this hook runs
            # BEFORE the server mints/adopts one, but the body already carries
            # the value the server will adopt). Otherwise mirror how the /prompt
            # route assigns the job number just after this handler returns; no
            # await happens in between.
            prompt_id = json_data.get("prompt_id")
            if prompt_id:
                name = prompt_id
            else:
                if "number" in json_data:
                    number = float(json_data["number"])
                elif json_data.get("front"):
                    number = -PromptServer.instance.number
                else:
                    number = PromptServer.instance.number
                # A queue number is NOT unique: it restarts at 0 on every ComfyUI
                # restart, so a bare "<number>.json" silently overwrites an earlier
                # run's workflow. Stamp the fallback so a collision cannot destroy
                # history. Submissions that carry a prompt_id keep naming by it.
                name = f"{number:g}-{time.strftime('%Y%m%d-%H%M%S')}"

            os.makedirs(QUEUED_DIR, exist_ok=True)
            with open(os.path.join(QUEUED_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(workflow, f)
    except Exception:
        pass  # never interfere with /prompt
    return json_data


PromptServer.instance.add_on_prompt_handler(_save_queued_workflow)

# This pack contributes no nodes. The empty mapping is what makes ComfyUI treat
# the module as a loaded custom-node package rather than skipping it.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
