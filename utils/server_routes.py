import os
import logging

import server
from aiohttp import web

logger = logging.getLogger(__name__)


@server.PromptServer.instance.routes.get("/cocotools/browse")
async def browse_directory(request):
    """Return directory listing with optional extension filtering."""
    query = request.rel_url.query
    path = query.get("path", "").strip()
    extensions = query.get("extensions", "").strip()

    ext_set = set()
    if extensions:
        ext_set = {e.strip().lower().lstrip(".") for e in extensions.split(",")}

    # No path provided — return starting points
    if not path:
        items = []
        home = os.path.expanduser("~")
        if os.path.isdir(home):
            items.append({"name": os.path.basename(home) or "home", "path": home, "type": "directory"})
        # Add OS roots
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.isdir(drive):
                    items.append({"name": drive, "path": drive, "type": "directory"})
        else:
            items.append({"name": "/", "path": "/", "type": "directory"})
        return web.json_response({"path": "", "parent": "", "items": items})

    # Normalize and validate path
    path = os.path.normpath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return web.json_response(
            {"error": f"Not a directory: {path}"},
            status=400,
        )

    parent = os.path.dirname(path)
    if parent == path:
        parent = ""

    items = []
    try:
        entries = os.listdir(path)
    except PermissionError:
        return web.json_response(
            {"error": f"Permission denied: {path}"},
            status=403,
        )

    dirs = []
    files = []

    for entry in entries:
        # Skip hidden files
        if entry.startswith("."):
            continue
        full = os.path.join(path, entry)
        try:
            if os.path.isdir(full):
                dirs.append({"name": entry, "type": "directory"})
            elif os.path.isfile(full):
                ext = os.path.splitext(entry)[1].lower().lstrip(".")
                if ext_set and ext not in ext_set:
                    continue
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                files.append({"name": entry, "type": "file", "size": size})
        except OSError:
            continue

    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    items = dirs + files

    return web.json_response({"path": path, "parent": parent, "items": items})
