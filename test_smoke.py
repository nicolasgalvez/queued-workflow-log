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


SAMPLE_ID = "6f9619ff-8b86-4d01-b42d-00cf4fc964ff"


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
    # still logs, named by the job number.
    handler({"number": 42, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [1]}}}})
    expected = os.path.join(tmp_dir, "queued", "42.json")
    assert os.path.exists(expected), f"expected {expected} to exist"
    with open(expected) as f:
        assert json.load(f) == {"nodes": [1]}
    print("OK:", expected)

    # A name collision must NOT destroy the existing file. Suffix like any normal
    # system: 42.json, then 42_1.json, then 42_2.json.
    handler({"number": 42, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [2]}}}})
    handler({"number": 42, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [3]}}}})
    got = sorted(f for f in os.listdir(os.path.join(tmp_dir, "queued")) if f.startswith("42"))
    assert got == ["42.json", "42_1.json", "42_2.json"], f"bad collision names: {got}"
    for name, expect in (("42.json", [1]), ("42_1.json", [2]), ("42_2.json", [3])):
        with open(os.path.join(tmp_dir, "queued", name)) as f:
            assert json.load(f) == {"nodes": expect}, f"{name} holds the wrong workflow"
    print("OK: collisions suffixed —", got)

    # The prompt_id path collides too (a resubmitted job id) and must suffix, not clobber.
    handler({"prompt_id": SAMPLE_ID, "extra_data": {"extra_pnginfo": {"workflow": {"nodes": [9]}}}})
    assert os.path.exists(os.path.join(tmp_dir, "queued", f"{SAMPLE_ID}_1.json")), \
        "a repeated prompt_id must suffix, not overwrite"
    print("OK: repeated prompt_id suffixed")


if __name__ == "__main__":
    main()
