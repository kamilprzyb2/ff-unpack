"""The `world` sub-pack: the map tiles and what goes with them.

    tile/<XX_YY>.glb    every map tile scene (Map_XX_YY), exported whole by
                        UnityPackFF: props, terrain (shifts applied, splat and
                        control maps, lightmap and grass in the material's
                        extras), animated props with their clips, lights, and
                        the scene's fog and colours in its extras; at its
                        world position
    shared/             images and mesh data, named by their content
    attr/<XX_YY>.bin    the tile's MapAttributeTable, 129 x 129 bytes
    sky/<set>/skybox_<side>tex.png  the two skyboxes
    bgm/<file>.ogg      the music and ambient tracks

The manifest lists the tiles, the music and ambient zones (MusicDataStorage)
and the main directional light. Nothing is rendered."""

import math
import os
import re

from unitypack.gltf import TERRAIN_COLLIDER, ExternalFiles, GLTFWriter, mirror_position
from unitypack.mapdata import ATTRIBUTE_HEAL, ATTRIBUTE_POISON, map_attributes, music_zones

from ..client import Client
from ..pack import safe
from .common import AUDIO_CLIP, MAIN, MATERIAL, basename, find, progress, texture_png, write_bytes
from .prefabs import GENERATOR, write_glb

SUBPACK = "world"
TILE = re.compile(r"^Map_(\d\d)_(\d\d)\.unity3d$")
LIGHT = 108
SKIES = {"skybox": "normal", "skybox_freezone": "fusion"}
SKY_SIDES = ("front", "back", "left", "right", "up", "down")
# cnPlayerCamera shows Skybox_FreeZone inside these rectangles (x, y,
# width, height in metres): the Future and the tutorial square.
FUSION_RECTS = [[5632, 512, 2048, 2048], [512, 512, 512, 512]]


def is_sky(e):
    return e.class_id == MATERIAL and basename(e.path) in SKIES


def is_track(e):
    return e.class_id == AUDIO_CLIP and e.path.startswith("bgm/")


def tiles(build):
    return sorted(a for a in build.archives() if TILE.match(a))


def toward_light(q):
    """The direction towards a directional light with rotation q (x, y, z,
    w; Unity's lights shine along their +z), in glTF's mirrored space."""
    x, y, z, w = q
    forward = [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]
    toward = mirror_position([-c for c in forward])
    n = math.sqrt(sum(c * c for c in toward)) or 1.0
    return [round(c / n, 6) for c in toward]


def light(client):
    """main.unity3d's directional light: the sun every tile is lit by.
    Direction towards the light, in glTF's (mirrored) space."""
    for name in client.files(MAIN):
        for obj in client.asset(name).objects.values():
            if obj.type_id != LIGHT:
                continue
            f = obj.read()
            f = getattr(f, "_obj", f)
            if f["m_Type"] != 1 or not f.get("m_Enabled", True):
                continue
            go = f["m_GameObject"].resolve()
            transform = next(ptr.resolve() for cid, ptr in go.component if cid == 4)
            q = getattr(transform, "_obj", transform)["m_LocalRotation"]
            color = f["m_Color"]
            return {"direction": toward_light([q[k] for k in "xyzw"]),
                    "color": [float(color[k]) for k in "rgb"], "intensity": float(f["m_Intensity"])}
    return None


def zones(client):
    """MusicDataStorage's music and ambient zones, from main.unity3d."""
    for name in client.files(MAIN):
        found = music_zones(client.asset(name))
        if found is not None:
            return {
                kind: [{"index": z.index, "name": z.name, "file": safe(z.file) if z.file else None,
                        "delay": z.delay, "instance": z.instance, "points": [list(p) for p in z.points]}
                       for z in found[kind]]
                for kind in ("music", "ambient")
            }
    raise RuntimeError("main.unity3d has no MusicDataStorage")


def skies(client, archives, staging):
    """The skybox materials' six faces (RenderFX/Skybox)."""
    done = []
    for e in find(client, archives, is_sky):
        mat = client.object(e).read()
        envs = {(k["name"] if hasattr(k, "keys") else k): v for k, v in mat._obj["m_SavedProperties"]["m_TexEnvs"]}
        name = SKIES[basename(e.path)]
        for side in SKY_SIDES:
            ptr = envs[f"_{side.capitalize()}Tex"]["m_Texture"]
            write_bytes(staging.path("sky", name, f"skybox_{side}tex.png"), texture_png(ptr.resolve()))
        done.append(name)
    return sorted(done)


# --- tiles, one process each -------------------------------------------------

_client = None


def _init(build, cache):
    global _client
    import logging

    logging.disable(logging.WARNING)
    _client = Client(build, cache, quiet=True)


def _tile(task):
    archive, out, shared = task
    tile = "_".join(TILE.match(archive).groups())
    try:
        scene = next(f for f in _client.files(archive) if not f.lower().endswith(".sharedassets"))
        asset = _client.asset(scene)
        if asset.objects and not asset.tree.type_trees:
            # Map_16..23_12..15 of 104 and 728: no type trees, so nothing
            # in them can be read (UnityPackFF's README)
            return tile, {"error": "no type trees"}
        w = GLTFWriter(generator=GENERATOR, external=ExternalFiles(shared))
        w.add_scene(asset)
        write_glb(w, os.path.join(out, "tile", f"{tile}.glb"))
        info = {"terrain": any(o.type_id == TERRAIN_COLLIDER for o in asset.objects.values())}
        attrs = map_attributes(asset)
        if attrs is not None:
            write_bytes(os.path.join(out, "attr", f"{tile}.bin"), attrs.values)
            info["attributes"] = {"size": attrs.size, "poison": len(attrs.cells(ATTRIBUTE_POISON)),
                                  "heal": len(attrs.cells(ATTRIBUTE_HEAL))}
        if w.warnings:
            info["warnings"] = len(w.warnings)
        return tile, info
    except Exception as e:  # one broken tile shouldn't stop the rest
        return tile, {"error": f"{type(e).__name__}: {e}"}


def export_tiles(client, staging, jobs):
    import multiprocessing

    tasks = [(a, staging.dir, staging.path("shared")) for a in tiles(client.build)]
    out = {}
    # Large tiles take over a gigabyte each; a fresh process every few
    # tiles keeps that from piling up.
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(jobs, initializer=_init, initargs=(client.build.protocol, client.cache), maxtasksperchild=4) as pool:
        for i, (tile, info) in enumerate(pool.imap_unordered(_tile, tasks), 1):
            out[tile] = info
            progress(client, "tiles", i, len(tasks))
    return dict(sorted(out.items()))


class World:
    name = "world"
    subpack = SUBPACK
    fixed = [MAIN]

    @staticmethod
    def seed(e):
        return is_sky(e) or is_track(e)

    @staticmethod
    def archives(build):
        return tiles(build)

    @staticmethod
    def run(client, staging, archives, jobs):
        found = export_tiles(client, staging, jobs)
        exported = {t: i for t, i in found.items() if "error" not in i}
        skipped = {t: i["error"] for t, i in found.items() if "error" in i}

        tracks = []
        for e in find(client, archives, is_track):
            data = bytes(client.object(e).read()._obj["audio data"] or b"")
            if data[:4] != b"OggS":
                client.log(f"  warning: {e.path} is not Ogg Vorbis inside; skipped")
                continue
            name = safe(e.path.split("/", 1)[1])
            write_bytes(staging.path("bgm", name), data)
            tracks.append(name)
        music = zones(client)
        for kind, zs in music.items():
            for z in zs:
                if z["file"] and z["file"] not in tracks:
                    client.log(f"  warning: {kind} zone {z['index']} plays {z['file']}, which isn't in the client")

        staging.manifest.update(
            tiles=exported,
            skipped=skipped,
            sky={"sets": skies(client, archives, staging), "fusion_rects": FUSION_RECTS},
            light=light(client),
            tracks=sorted(tracks),
            **music,
        )
        poison = sum(1 for i in exported.values() if i.get("attributes", {}).get("poison"))
        return (f"{len(exported)} tiles ({len(skipped)} unreadable, {poison} with poison), "
                f"{len(tracks)} tracks, {len(music['music'])} music and {len(music['ambient'])} ambient zones")
