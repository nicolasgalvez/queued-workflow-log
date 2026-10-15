# Queued Workflow Log

Writes the workflow of every queued job to `<ComfyUI user directory>/queued/`, in UI format —
the same JSON you get from Workflow → Export, so it opens straight onto the canvas.

Every queued job must carry that workflow. A job submitted without one is refused before it
queues (see [Jobs without a workflow](#jobs-without-a-workflow)), so every run that happens has
a record you can reopen.

Headless: no nodes, no UI, no settings, no dependencies. Installing it and restarting ComfyUI is
the whole configuration. Nothing has to be added to a workflow for it to be captured.

## Filenames

`<datetime>-<hash>.json`, always — millisecond-resolution local time plus a short random
suffix, e.g. `20260909-212733-481-d3f07a.json`. The suffix keeps two same-millisecond
submissions distinct. Never the queue number: it restarts at 0 on every ComfyUI restart,
so `1.json, 2.json…` collide and say nothing about which run they came from.

The file is created with `open(..., "x")`, so an existing log is never truncated. A name
collision raises `FileExistsError`; ComfyUI core catches on_prompt handler errors, logs the
traceback, and the queue proceeds.

## Jobs without a workflow

Queuing from the ComfyUI canvas attaches the workflow automatically. A script, agent or API
client that posts only the API `prompt` to `POST /prompt` (or `/api/prompt`) gets HTTP 400 and
nothing queues:

```json
{
  "error": {
    "type": "workflow_required",
    "message": "Rejected: this job has no workflow attached. queued-workflow-log requires every queued job to carry its UI workflow so the run can be saved and reopened.",
    "details": "The request body has no extra_data object. Include extra_data.extra_pnginfo.workflow in the request body, …",
    "extra_info": {
      "required_field": "extra_data.extra_pnginfo.workflow",
      "reason": "extra_data_missing",
      "received_extra_data_keys": [],
      "pack": "queued-workflow-log",
      "docs": "https://github.com/nicolasgalvez/queued-workflow-log#readme"
    }
  },
  "node_errors": {}
}
```

`reason` is one of `extra_data_missing`, `extra_pnginfo_missing`, `workflow_missing` and
`workflow_not_object`. ComfyUI's log gets one WARNING line per refusal, with the `client_id`
and the reason.

**The fix:** include `extra_data.extra_pnginfo.workflow` in the request body, set to the
UI-format workflow JSON the API prompt was converted from: the file from Workflow → Save or
Export, i.e. the canvas graph with `nodes` and `links`.

```json
{"prompt": {"<API graph>": "…"}, "extra_data": {"extra_pnginfo": {"workflow": {"<UI workflow>": "…"}}}, "client_id": "…"}
```

The accepted job's workflow is saved to `<user dir>/queued/<datetime>-<hash>.json` and embedded
in its outputs, so "open workflow" works.

Only `POST /prompt` and `POST /api/prompt` are checked. Other routes, other methods, and bodies
that are not a JSON object pass through to ComfyUI's own handling unchanged.

## Install

Clone into ComfyUI's `custom_nodes/`, then restart ComfyUI:

    git clone git@github.com:nicolasgalvez/queued-workflow-log.git \
              /path/to/ComfyUI/custom_nodes/queued-workflow-log

Do **not** symlink it from another checkout if ComfyUI runs in Docker — the link target is
outside the container's mount namespace and the symlink dangles.

## Implementation note

ComfyUI's documentation covers node classes, new HTTP routes, and custom WebSocket messages; it
documents no server-side hook on the queue-submission path. This pack uses two undocumented ones:

- `PromptServer.instance.add_on_prompt_handler`, a long-standing hook in ComfyUI core, invoked
  at the top of the `POST /prompt` route. It saves the workflow. It cannot refuse a job:
  core's `trigger_on_prompt` catches any exception a handler raises, logs it, and queues the
  job anyway.
- So the refusal is an aiohttp middleware appended to `PromptServer.instance.app.middlewares`.
  Custom nodes import after `PromptServer()` builds the app and before the server starts, so
  the list is still open. The middleware reads the body with `await request.json()`; aiohttp
  caches it, so the route reads it again unchanged. A pack loaded after startup would fail to
  import with `Cannot modify frozen list` rather than run unchecked.

## Test

Needs aiohttp, which ComfyUI already depends on:

    python3 test_smoke.py
