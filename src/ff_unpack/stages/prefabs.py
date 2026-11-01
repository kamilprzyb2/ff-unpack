"""Exporting prefabs (GameObjects in a container) to glTF with UnityPackFF,
for the avatar and models sub-packs.

A prefab goes to a folder of its own, <kind>/<model>/:

    <variant>.glb       the model, once per set of textures the XDT puts on
                        it (named by the set's first texture), or default.glb
                        with the prefab's own when the XDT names none
    clips/<clip>.glb    each animation clip on its own: the same nodes in the same
                        order, no meshes, so it plays on any variant

Images and mesh data go to the sub-pack's shared/ folder, named by their
content, so variants and prefabs that use the same texture or mesh share
one file."""

import os
import sys
from collections import namedtuple

from unitypack.gltf import ExternalFiles, GLTFWriter
from unitypack.xdttextures import prefab_key, texture_swaps, worn_prefabs

from .. import __version__
from ..client import Client
from ..gltfclip import compact
from ..pack import safe
from .common import GAME_OBJECT, TEXTURE_2D, TRANSFORM, find, xdt

GENERATOR = f"ff-unpack {__version__} (UnityPackFF)"

Job = namedtuple("Job", "build cache archives shared out actor_bones as_worn")


def gameobject(client, entry):
    """The GameObject a container entry loads (some name its Transform)."""
    obj = client.object(entry)
    if obj.type_id == TRANSFORM:
        return obj.read().game_object.resolve()
    if obj.type_id == GAME_OBJECT:
        return obj.read()
    return None


def is_texture(e):
    return e.path.startswith("texture/") and e.class_id == TEXTURE_2D


class Textures:
    """The client's "texture/<name>.dds" entries, which the XDT names."""

    def __init__(self, client, archives):
        self.client = client
        self.entries = {e.path: e for e in find(client, archives, is_texture)}
        self.loaded = {}

    def entry(self, name):
        return self.entries.get(f"texture/{name.lower()}.dds")

    def get(self, name):
        if name not in self.loaded:
            e = self.entry(name)
            self.loaded[name] = self.client.object(e).read() if e is not None else None
        return self.loaded[name]


def override(swap, textures, missing):
    """A texture_override for GLTFWriter that applies one XDT texture set."""

    def choose(material, slot):
        name = swap.texture_for(material.name, slot)
        if name is None:
            return None
        texture = textures.get(name)
        if texture is None:
            missing.add(name)  # as in the game, the material keeps its own
        return texture

    return choose


def variant_names(sets):
    """A file name for each texture set: its first texture, or both when
    that's not enough to tell them apart."""
    if sets == [None]:
        return ["default"]
    names = [safe(s.main or s.sub) for s in sets]
    if len(set(names)) < len(names):
        names = [safe("+".join(t for t in (s.main, s.sub) if t)) for s in sets]
    seen, out = {}, []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}-{seen[n]}")
    return out


def glb_bytes(writer, folder):
    """A GLTFWriter's .glb, for a file in folder (shared files' URIs are
    relative to it). A document whose data all went to shared files gets an
    empty 4-byte BIN chunk anyway: glTF allows a .glb without one, but VTK
    before 9.6 (F3D, its thumbnailer) rejects it."""
    if not writer.bin:
        writer.bin = bytearray(4)
    return writer.glb(folder)


def write_glb(writer, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(glb_bytes(writer, os.path.dirname(path)))
    os.replace(tmp, path)


class Exporter:
    """One process's view of the client for exporting prefabs: the XDT's
    texture sets and the texture index are built once."""

    def __init__(self, job):
        self.job = job
        self.client = Client(job.build, job.cache, quiet=True)
        table = xdt(self.client)
        self.swaps = texture_swaps(table)
        self.worn_all = worn_prefabs(table)
        self.worn = self.worn_all if job.as_worn else set()
        self.textures = Textures(self.client, job.archives)
        self.external = ExternalFiles(job.shared)

    def export(self, entry, folder):
        """Writes one prefab to folder (relative to the sub-pack); returns
        what the manifest lists for it."""
        go = gameobject(self.client, entry)
        if go is None:
            return {"error": "not a prefab"}
        key = prefab_key(entry.path)
        sets = self.swaps.get(key, [None])
        out = {"source": entry.archive, "variants": {}, "clips": {}}
        warnings, missing, left_out, unbound = [], set(), 0, []
        for i, (swap, name) in enumerate(zip(sets, variant_names(sets))):
            w = GLTFWriter(
                generator=GENERATOR,
                texture_override=override(swap, self.textures, missing) if swap else None,
                external=self.external,
            )
            # Clips are the same for every variant: sampled once.
            w.add_gameobject(go, animations=i == 0, skinned_only=key in self.worn, actor_bones=self.job.actor_bones)
            base, clips = w.split_clips()
            file = f"{folder}/{name}.glb"
            write_glb(base, os.path.join(self.job.out, file))
            out["variants"][name] = {"file": file, **({"textures": [t for t in (swap.main, swap.sub)]} if swap else {})}
            if i == 0:
                warnings += w.warnings
                left_out, unbound = len(w.left_out), list(w.unbound_skins)
                seen = {}
                for clip, cw in clips:
                    n = safe(clip)
                    seen[n] = seen.get(n, 0) + 1
                    n = n if seen[n] == 1 else f"{n}-{seen[n]}"
                    file = f"{folder}/clips/{n}.glb"
                    write_glb(compact(cw), os.path.join(self.job.out, file))
                    out["clips"].setdefault(clip, file)
        if not out["clips"]:
            del out["clips"]
        if missing:
            warnings += [f"no texture/{t}.dds in the client; kept the prefab's own" for t in sorted(missing)]
        if key in self.worn and left_out:
            out["left_out"] = left_out
        if unbound and key in self.worn_all:
            warnings += [f"{m} has no ActorWearIndexTable: it can't be bound to the character" for m in unbound]
        if warnings:
            out["warnings"] = warnings
        return out


_exporter = None


def _init(job):
    global _exporter
    import logging

    logging.disable(logging.WARNING)
    _exporter = Exporter(job)


def _work(task):
    entry, folder = task
    try:
        return entry.path, _exporter.export(entry, folder)
    except Exception as e:  # one broken prefab shouldn't stop the rest
        return entry.path, {"error": f"{type(e).__name__}: {e}"}


def export_all(client, job, tasks, jobs, label):
    """Exports [(entry, folder)] over a process pool; returns {path: result}."""
    from .common import progress

    results = {}
    if jobs <= 1:
        _init(job)
        for i, t in enumerate(tasks, 1):
            path, r = _work(t)
            results[path] = r
            progress(client, label, i, len(tasks))
    else:
        import multiprocessing

        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(jobs, initializer=_init, initargs=(job,)) as pool:
            for i, (path, r) in enumerate(pool.imap_unordered(_work, tasks, chunksize=4), 1):
                results[path] = r
                progress(client, label, i, len(tasks))
    for path, r in sorted(results.items()):
        if "error" in r:
            print(f"  warning: {path}: {r['error']}", file=sys.stderr)
    return results
