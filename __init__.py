"""Refuse queued jobs that carry no UI workflow; save every workflow that is
queued to <user dir>/queued/<datetime>-<hash>.json.

A POST /prompt (or /api/prompt) whose JSON body has no
extra_data.extra_pnginfo.workflow object is answered 400 workflow_required
before ComfyUI queues it, with the reason and the fix in the response. The
ComfyUI canvas always attaches the workflow; a bare API prompt from a script
does not, and leaves no record that can be reopened.

Workflow files are named by wall-clock time (millisecond resolution) plus a
short random suffix, e.g. 20260909-212733-481-d3f07a.json. Never the queue
number: it restarts at 0 on every ComfyUI restart, so 1.json, 2.json...
collide and say nothing about which run they came from.

Headless: this pack contributes no nodes and no UI. Its entire effect is this
module's import, per the documented custom-node lifecycle
(https://docs.comfy.org/custom-nodes/backend/lifecycle).

NOTE: neither hook used here is documented on docs.comfy.org.
- PromptServer.add_on_prompt_handler is a long-standing hook in ComfyUI core
  (server.py: invoked from trigger_on_prompt at the top of the POST /prompt
  route). It cannot refuse a job: trigger_on_prompt catches every exception a
  handler raises, logs it, and queues the job anyway.
- So the refusal is an aiohttp middleware appended to PromptServer.instance.app.
  Custom nodes import after PromptServer() builds the app and before the
  AppRunner starts it (main.py: PromptServer, then init_extra_nodes, then
  start), so the middleware list is still open to append to.
"""

import json
import logging
import os
import secrets
from datetime import datetime

import folder_paths
from aiohttp import web
from server import PromptServer

QUEUED_DIR = os.path.join(folder_paths.get_user_directory(), "queued")
PROMPT_PATHS = frozenset({"/prompt", "/api/prompt"})
REQUIRED_FIELD = "extra_data.extra_pnginfo.workflow"
DOCS = "https://github.com/nicolasgalvez/queued-workflow-log#readme"

log = logging.getLogger("queued-workflow-log")

MESSAGE = (
    "Rejected: this job has no workflow attached. queued-workflow-log requires every "
    "queued job to carry its UI workflow so the run can be saved and reopened."
)
REASONS = {
    "extra_data_missing": "The request body has no extra_data object.",
    "extra_pnginfo_missing": "extra_data has no extra_pnginfo object.",
    "workflow_missing": "extra_data.extra_pnginfo has no workflow.",
    "workflow_not_object": "extra_data.extra_pnginfo.workflow is not a JSON object.",
}
FIX = (
    "Include extra_data.extra_pnginfo.workflow in the request body, set to the UI-format "
    "workflow JSON the API prompt was converted from: the file from Workflow -> Save or "
    "Export, i.e. the canvas graph with nodes and links. Body shape: "
    '{"prompt": {<API graph>}, "extra_data": {"extra_pnginfo": {"workflow": {<UI workflow>}}}, '
    '"client_id": "..."}. Queuing from the ComfyUI canvas does this automatically. The '
    "accepted job's workflow is saved to <user dir>/queued/<datetime>-<hash>.json and "
    'embedded in its outputs, so "open workflow" works.'
)


def _missing_workflow(body):
    """Why body carries no UI workflow (a REASONS key), or None if it does."""
    extra_data = body.get("extra_data")
    if not isinstance(extra_data, dict):
        return "extra_data_missing"
    extra_pnginfo = extra_data.get("extra_pnginfo")
    if not isinstance(extra_pnginfo, dict):
        return "extra_pnginfo_missing"
    if "workflow" not in extra_pnginfo or extra_pnginfo["workflow"] is None:
        return "workflow_missing"
    if not isinstance(extra_pnginfo["workflow"], dict):
        return "workflow_not_object"
    return None


def _refusal_response(body, reason):
    extra_data = body.get("extra_data")
    error = {
        "type": "workflow_required",
        "message": MESSAGE,
        "details": f"{REASONS[reason]} {FIX}",
        "extra_info": {
            "required_field": REQUIRED_FIELD,
            "reason": reason,
            "received_extra_data_keys": sorted(extra_data) if isinstance(extra_data, dict) else [],
            "pack": "queued-workflow-log",
            "docs": DOCS,
        },
    }
    return web.json_response({"error": error, "node_errors": {}}, status=400)


@web.middleware
async def _require_workflow(request, handler):
    if request.method != "POST" or request.path not in PROMPT_PATHS:
        return await handler(request)
    try:
        # aiohttp caches the body, so the route's own request.json() reads it again.
        body = await request.json()
    except ValueError:
        return await handler(request)  # malformed: ComfyUI's own handling
    if not isinstance(body, dict):
        return await handler(request)
    reason = _missing_workflow(body)
    if reason is None:
        return await handler(request)
    log.warning(
        "[queued-workflow-log] Rejected POST %s (client_id=%s): %s",
        request.path, body.get("client_id"), reason,
    )
    return _refusal_response(body, reason)


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


PromptServer.instance.app.middlewares.append(_require_workflow)
PromptServer.instance.add_on_prompt_handler(_save_queued_workflow)

# This pack contributes no nodes. The empty mapping is what makes ComfyUI treat
# the module as a loaded custom-node package rather than skipping it.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
