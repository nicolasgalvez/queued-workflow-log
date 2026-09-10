"""Smoke test: every queued workflow is saved once, named
<datetime>-<hash>.json — never a bare queue number.

Not a test suite -- stdlib only, run directly:
    python3 test_smoke.py
"""

import importlib
import json
import os
import re
import sys
import tempfile
import types


# 20260909-212733-481-d3f07a.json
STAMPED = re.compile(r"^\d{8}-\d{6}-\d{3}-[0-9a-f]{6}\.json$")


def main():
    tmp_dir = tempfile.mkdtemp()

    fake_folder_paths = types.ModuleType("folder_paths")
    fake_folder_paths.get_user_directory = lambda: tmp_dir

    class FakePromptServer:
        instance = None

        def __init__(self):
            self.handlers = []

        def add_on_prompt_handler(self, fn):
            self.handlers.append(fn)

    fake_server = types.ModuleType("server")
    fake_server.PromptServer = FakePromptServer
    FakePromptServer.instance = FakePromptServer()

    sys.modules["folder_paths"] = fake_folder_paths
    sys.modules["server"] = fake_server

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    importlib.import_module("__init__")

    handler = FakePromptServer.instance.handlers[0]
    queued = os.path.join(tmp_dir, "queued")

    # Same body, twice, as fast as the loop can go — two same-millisecond
    # submissions must still produce two distinct stamped files.
    body = {"extra_data": {"extra_pnginfo": {"workflow": {"nodes": [1]}}}}
    handler(body)
    handler(body)

    files = os.listdir(queued)
    assert len(files) == 2, f"expected 2 logs, got {sorted(files)}"
    for name in files:
        assert STAMPED.match(name), f"not a datetime+hash name: {name}"
        with open(os.path.join(queued, name)) as f:
            assert json.load(f) == {"nodes": [1]}, f"{name} holds the wrong workflow"
    assert not [f for f in files if re.match(r"^\d+(_\d+)?\.json$", f)], "a queue-number filename was produced"
    print("OK:", ", ".join(sorted(files)))


if __name__ == "__main__":
    main()
