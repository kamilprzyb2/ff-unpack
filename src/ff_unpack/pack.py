"""Writing a sub-pack: staged next to its final place and swapped in whole,
with its manifest (PACK_FORMAT.md, "Manifests")."""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

import unitypack

from . import __version__

FORMAT_VERSION = 1


def safe(name):
    """A client name as a file name: lowercase, anything but letters, digits,
    `_`, `.`, `-`, `@` and `+` as `_`."""
    return re.sub(r"[^a-z0-9_.@+-]+", "_", name.lower())


def fingerprint(sources, tools=None):
    """One SHA-256 over the sources ({archive: sha256}) and what exported
    them (tools: {name: version}): the same for the same input and the same
    exporter, whenever the pack was made."""
    h = hashlib.sha256()
    for name in sorted(sources):
        h.update(f"{name}\t{sources[name]}\n".encode())
    for name in sorted(tools or {}):
        h.update(f"tool\t{name}\t{tools[name]}\n".encode())
    return h.hexdigest()


def unitypackff_version():
    """UnityPackFF's version, with its commit when it runs from a checkout."""
    version = {"version": getattr(unitypack, "__version__", None)}
    folder = os.path.dirname(os.path.dirname(os.path.abspath(unitypack.__file__)))
    try:
        commit = subprocess.run(
            ["git", "-C", folder, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except OSError:
        commit = ""
    if commit:
        version["commit"] = commit
        # a checkout with uncommitted changes isn't that commit
        dirty = subprocess.run(
            ["git", "-C", folder, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if dirty:
            version["dirty"] = True
    return version


def write_json(path, data, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if compact:
            json.dump(data, f, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
        else:
            json.dump(data, f, indent=1, allow_nan=False, ensure_ascii=False)
        f.write("\n")


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Staging:
    """A sub-pack being written: `with Staging(out, build, "base") as s:`
    write into s.dir, set s.sources and s.manifest; on success it replaces
    <out>/<build>/<subpack>/ in one rename, so a reader never sees half a
    pack. On failure the old pack stays."""

    def __init__(self, out, build, subpack):
        self.build = build
        self.subpack = subpack
        self.parent = os.path.join(out, build.name)
        self.final = os.path.join(self.parent, subpack)
        self.sources = {}
        self.manifest = {}
        self.work = None
        self.dir = None

    def __enter__(self):
        os.makedirs(self.parent, exist_ok=True)
        self.work = tempfile.mkdtemp(prefix=f".{self.subpack}-", dir=self.parent)
        self.dir = os.path.join(self.work, self.subpack)
        os.makedirs(self.dir)
        return self

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def header(self):
        upff = unitypackff_version()
        tools = {
            "format_version": FORMAT_VERSION,
            "ff_unpack": __version__,
            "unitypackff": (upff.get("commit") or upff.get("version")) + ("+dirty" if upff.get("dirty") else ""),
        }
        return {
            "format": f"ff-unpack/{self.subpack}",
            "format_version": FORMAT_VERSION,
            "build": self.build.as_json(),
            "ff_unpack": __version__,
            "unitypackff": upff,
            "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": dict(sorted(self.sources.items())),
            "fingerprint": fingerprint(self.sources, tools),
        }

    def __exit__(self, kind, value, tb):
        try:
            if kind is None:
                write_json(self.path("manifest.json"), {**self.header(), **self.manifest}, compact=False)
                old = os.path.join(self.work, "old")
                if os.path.exists(self.final):
                    os.rename(self.final, old)
                os.rename(self.dir, self.final)
        finally:
            shutil.rmtree(self.work, ignore_errors=True)
        return False
