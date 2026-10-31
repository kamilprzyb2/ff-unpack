"""Helpers the stages share: finding things in the client, and turning them
into plain files."""

import io
import math
import os

from unitypack.object import ObjectPointer

TEXTURE_2D = 28
MATERIAL = 21
GAME_OBJECT = 1
TRANSFORM = 4
AUDIO_CLIP = 83
MONO_BEHAVIOUR = 114
TABLEDATA = "TableData.resourceFile"
MAIN = "main.unity3d"


def basename(path):
    """A container path's file name without its extension."""
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def find(client, archives, match):
    """Container entries of the archives that match(entry), each load path
    once (the first archive listed wins)."""
    seen, out = set(), []
    for archive in archives:
        for e in client.entries(archive):
            if e.path not in seen and match(e):
                seen.add(e.path)
                out.append(e)
    return out


def needed(client, archives, jobs=4):
    """The archives, plus every archive their files point into, and so on:
    what must be unpacked for pointers to resolve. Fetches them all."""
    done, todo = set(), sorted(set(archives))
    while todo:
        client.fetch(todo, jobs)
        done.update(todo)
        pointed = set()
        for a in todo:
            for f in client.files(a):
                pointed |= client.externals(f)
        todo = sorted(pointed - done)
    return sorted(done)


def png(image):
    """A PIL image in Unity's orientation (bottom row first, as
    Texture2D.image gives it) as PNG bytes, upright. The same pixels give
    the same bytes."""
    from PIL import ImageOps

    out = io.BytesIO()
    ImageOps.flip(image).save(out, format="png")
    return out.getvalue()


def texture_png(texture):
    """A Texture2D as upright PNG bytes, or None if it has no image."""
    image = texture.image
    return png(image) if image is not None else None


def to_json(value):
    """A read value as plain JSON: colours as [r, g, b, a], pointers as
    {"file_id", "path_id"} (null for none), byte arrays as lists."""
    if isinstance(value, ObjectPointer):
        return {"file_id": value.file_id, "path_id": value.path_id} if value else None
    if hasattr(value, "_obj"):
        value = value._obj
    if isinstance(value, dict):
        if set(value) == {"r", "g", "b", "a"}:
            return [float(value[k]) for k in "rgba"]
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def script_rows(obj, field):
    """A script object's table (its list field) as plain JSON rows."""
    return to_json(obj.read()[field])


def xdt(client):
    """TableData's XDT (xdtdatas.asset), read."""
    entry = next(e for e in client.entries(TABLEDATA) if e.path == "xdtdatas.asset")
    return client.object(entry).read()


def tables(table, wanted):
    """Some of the XDT's tables, as plain JSON: {table: {list: rows}} for
    wanted = {table: (list, ...)}."""
    out = {}
    for name, keys in wanted.items():
        t = table.get(name)
        if t is not None:
            out[name] = {k: to_json(t[k]) for k in keys if k in t}
    return out


def progress(client, label, done, total):
    """A progress line on a terminal, every 10% otherwise."""
    if client.quiet:
        return
    import sys

    if sys.stderr.isatty():
        print(f"\r  {label} {done}/{total}", end="" if done < total else "\n", file=sys.stderr, flush=True)
    elif total and (done == total or done * 10 // total != (done - 1) * 10 // total):
        print(f"  {label} {done}/{total}", file=sys.stderr, flush=True)


def jobs_pool(jobs):
    """A process pool for the stages that spread work over processes; each
    worker opens the cache on its own."""
    import multiprocessing

    return multiprocessing.get_context("spawn").Pool(max(1, jobs), maxtasksperchild=8)


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
