"""Smoke test: a job reaches the queue only with its UI workflow attached, and
every accepted workflow is saved once, named <datetime>-<hash>.json.

What change to our code makes this fail, and what it sees:
- the pack stops registering its middleware, or stops matching POST /prompt
  or /api/prompt: a bare API prompt is queued (200) instead of refused (400
  workflow_required), and nothing explains why;
- the middleware consumes the body so the route cannot read it again, or
  blocks a job that carries a workflow: the accepted job is not queued and
  its workflow file is not written;
- the middleware touches other methods, routes or malformed bodies: GET
  /prompt, POST /other, or ComfyUI's own malformed-body response changes;
- the error loses its fix text, its per-case reason, or the server-side
  warning: the assertions on message/details/extra_info/log fail;
- the filename drops the hash or reverts to the queue number: two
  same-millisecond saves collide, or a bare number appears.

Not a test suite -- run directly (needs aiohttp, which ComfyUI ships):
    python3 test_smoke.py
"""

import asyncio
import importlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import types

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


# 20260909-212733-481-d3f07a.json
STAMPED = re.compile(r"^\d{8}-\d{6}-\d{3}-[0-9a-f]{6}\.json$")
FIELD = "extra_data.extra_pnginfo.workflow"

PROMPT = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
WORKFLOW = {"nodes": [{"id": 3}], "links": []}


class FakePromptServer:
    """The parts of ComfyUI's PromptServer the pack touches: the aiohttp app
    (whose middleware list is still open while custom nodes import) and the
    on_prompt handler list, run the way server.trigger_on_prompt runs it."""

    instance = None

    def __init__(self):
        self.app = web.Application()
        self.handlers = []
        self.queued = []

    def add_on_prompt_handler(self, fn):
        self.handlers.append(fn)

    def trigger_on_prompt(self, json_data):
        for handler in self.handlers:
            try:
                json_data = handler(json_data)
            except Exception:
                logging.exception("on_prompt handler failed")
        return json_data


def load_pack(tmp_dir):
    fake_folder_paths = types.ModuleType("folder_paths")
    fake_folder_paths.get_user_directory = lambda: tmp_dir
    fake_server = types.ModuleType("server")
    fake_server.PromptServer = FakePromptServer
    FakePromptServer.instance = FakePromptServer()
    sys.modules["folder_paths"] = fake_folder_paths
    sys.modules["server"] = fake_server
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    importlib.import_module("__init__")
    return FakePromptServer.instance


def add_core_routes(server):
    """Stand-ins for ComfyUI core's routes, registered after the pack imports
    (as main.py does). post_prompt reads the body the way core does."""

    async def post_prompt(request):
        json_data = await request.json()  # core does not catch: malformed -> 500
        json_data = server.trigger_on_prompt(json_data)
        server.queued.append(json_data)
        return web.json_response({"prompt_id": "p", "number": len(server.queued)})

    async def get_prompt(request):
        return web.json_response({"exec_info": {"queue_remaining": 0}})

    async def post_other(request):
        return web.json_response({"other": await request.json()})

    for prefix in ("", "/api"):
        server.app.router.add_post(prefix + "/prompt", post_prompt)
        server.app.router.add_get(prefix + "/prompt", get_prompt)
    server.app.router.add_post("/other", post_other)


class Captured(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


async def http_checks(server, queued_dir, log):
    def saved():
        return sorted(os.listdir(queued_dir)) if os.path.isdir(queued_dir) else []

    async with TestClient(TestServer(server.app)) as client:
        # Each way a body can lack its workflow, on both paths core serves.
        cases = [
            ("/prompt", {"prompt": PROMPT, "client_id": "cli-1"},
             "extra_data_missing", []),
            ("/api/prompt", {"prompt": PROMPT, "extra_data": None},
             "extra_data_missing", []),
            ("/api/prompt", {"prompt": PROMPT, "extra_data": {"client_id": "x"}},
             "extra_pnginfo_missing", ["client_id"]),
            ("/prompt", {"prompt": PROMPT, "extra_data": {"extra_pnginfo": None}},
             "extra_pnginfo_missing", ["extra_pnginfo"]),
            ("/prompt", {"prompt": PROMPT, "extra_data": {"extra_pnginfo": {"other": 1}}},
             "workflow_missing", ["extra_pnginfo"]),
            ("/api/prompt", {"prompt": PROMPT, "extra_data": {"extra_pnginfo": {"workflow": "[]"}}},
             "workflow_not_object", ["extra_pnginfo"]),
        ]
        for path, body, reason, keys in cases:
            resp = await client.post(path, json=body)
            assert resp.status == 400, f"{path} {body}: expected 400, got {resp.status}"
            data = await resp.json()
            err = data["error"]
            assert err["type"] == "workflow_required", f"wrong error type: {err}"
            assert data["node_errors"] == {}, f"node_errors not empty: {data}"
            assert FIELD in err["details"], f"details do not name {FIELD}: {err['details']}"
            assert '"extra_pnginfo": {"workflow"' in err["details"], f"details show no body shape: {err['details']}"
            info = err["extra_info"]
            assert info["required_field"] == FIELD, info
            assert info["reason"] == reason, f"{body}: expected reason {reason}, got {info}"
            assert info["received_extra_data_keys"] == keys, f"{body}: expected keys {keys}, got {info}"
            assert info["pack"] == "queued-workflow-log", info
            assert info["docs"].startswith("https://github.com/nicolasgalvez/queued-workflow-log"), info
        assert server.queued == [], f"a job without a workflow was queued: {server.queued}"
        assert saved() == [], f"a job without a workflow was saved: {saved()}"
        assert len(log.lines) == len(cases), f"expected one warning per refusal, got {log.lines}"
        assert "cli-1" in log.lines[0] and "extra_data_missing" in log.lines[0], log.lines[0]

        # A job with its workflow goes through: the route still reads the
        # body after the middleware did, the job queues, the workflow saves.
        body = {"prompt": PROMPT, "extra_data": {"extra_pnginfo": {"workflow": WORKFLOW}}}
        for path in ("/prompt", "/api/prompt"):
            resp = await client.post(path, json=body)
            assert resp.status == 200, f"{path} with workflow: expected 200, got {resp.status}"
        assert server.queued == [body, body], f"accepted jobs not queued intact: {server.queued}"
        files = saved()
        assert len(files) == 2, f"expected 2 workflow logs, got {files}"
        for name in files:
            assert STAMPED.match(name), f"not a datetime+hash name: {name}"
            with open(os.path.join(queued_dir, name)) as f:
                assert json.load(f) == WORKFLOW, f"{name} holds the wrong workflow"

        # Untouched: other methods, other routes, malformed bodies.
        resp = await client.get("/prompt")
        assert resp.status == 200 and "exec_info" in await resp.json(), "GET /prompt changed"
        resp = await client.post("/other", json={"prompt": PROMPT})
        assert resp.status == 200 and await resp.json() == {"other": {"prompt": PROMPT}}, "POST /other changed"
        resp = await client.post("/prompt", data=b"{not json", headers={"Content-Type": "application/json"})
        assert resp.status == 500, f"malformed body did not reach core's handling: {resp.status} {await resp.text()}"


def main(tmp_dir):
    server = load_pack(tmp_dir)
    add_core_routes(server)
    queued_dir = os.path.join(tmp_dir, "queued")

    log = Captured()
    logging.getLogger().addHandler(log)
    try:
        asyncio.run(http_checks(server, queued_dir, log))
    finally:
        logging.getLogger().removeHandler(log)

    # Same body, twice, as fast as the loop can go — two same-millisecond
    # submissions must still produce two distinct stamped files.
    before = set(os.listdir(queued_dir))
    body = {"extra_data": {"extra_pnginfo": {"workflow": WORKFLOW}}}
    handler = server.handlers[0]
    handler(body)
    handler(body)
    files = sorted(set(os.listdir(queued_dir)) - before)
    assert len(files) == 2, f"expected 2 logs, got {files}"
    assert all(STAMPED.match(name) for name in files), f"not datetime+hash names: {files}"
    assert not [f for f in os.listdir(queued_dir) if re.match(r"^\d+(_\d+)?\.json$", f)], "a queue-number filename was produced"
    print("OK:", ", ".join(sorted(os.listdir(queued_dir))))


if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    try:
        main(tmp)
    finally:
        shutil.rmtree(tmp)
