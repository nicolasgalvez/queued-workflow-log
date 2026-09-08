"""Smoke test: the saved filename is the client-supplied prompt_id, falling
back to the job number when the body carries none.

Not a test suite -- stdlib only, run directly:
    python3 test_smoke.py
"""

import importlib
import json
import os
import re
import sys
import time
import tempfile
import types


def main():
    tmp_dir = tempfile.mkdtemp()

    fake_folder_paths = types.ModuleType("folder_paths")
    fake_folder_paths.get_user_directory = lambda: tmp_dir

    class FakePromptServer:
        instance = None

        def __init__(self):
            self.number = 42
            self.handlers = []

        def add_on_prompt_handler(self, fn):
            self.handlers.append(fn)

    fake_server = types.ModuleType("server")
    fake_server.PromptServer = FakePromptServer
    FakePromptServer.instance = FakePromptServer()

    sys.modules["folder_paths"] = fake_folder_paths
    sys.modules["server"] = fake_server

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    pack = importlib.import_module("__init__")

    handler = FakePromptServer.instance.handlers[0]

    # Client-supplied prompt_id (what the studio adapter and ComfyUI's own
    # frontend send): the file is named by that UUID, not the job number.
    prompt_id = "6f9619ff-8b86-4d01-b42d-00cf4fc964ff"
    handler(
        {
            "prompt_id": prompt_id,
            "extra_data": {"extra_pnginfo": {"workflow": {"nodes": []}}},
        }
    )
    expected_path = os.path.join(tmp_dir, "queued", f"{prompt_id}.json")
    assert os.path.exists(expected_path), f"expected {expected_path} to exist"
    with open(expected_path) as f:
        assert json.load(f) == {"nodes": []}
    print("OK:", expected_path)

    # Fallback: no prompt_id in the body (a frontend submission that omits it)
    # still logs. The name is the job number STAMPED with a timestamp: a bare
    # number is not unique (it restarts at 0 on every ComfyUI restart), so an
    # unstamped name silently overwrites an earlier run's workflow.
    handler({"number": 42, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [1]}}}})
    matches = [f for f in os.listdir(os.path.join(tmp_dir, "queued")) if f.startswith("42-")]
    assert len(matches) == 1, f"expected one 42-<stamp>.json, got {matches}"
    assert re.fullmatch(r"42-\d{8}-\d{6}\.json", matches[0]), f"bad name {matches[0]}"
    with open(os.path.join(tmp_dir, "queued", matches[0])) as f:
        assert json.load(f) == {"nodes": [1]}
    print("OK:", os.path.join(tmp_dir, "queued", matches[0]))

    # A second numbered submission must NOT destroy the first.
    time.sleep(1.1)
    handler({"number": 42, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [2]}}}})
    matches = sorted(f for f in os.listdir(os.path.join(tmp_dir, "queued")) if f.startswith("42-"))
    assert len(matches) == 2, f"collision destroyed history: {matches}"
    print("OK: no collision —", matches)


if __name__ == "__main__":
    main()
