"""The `world` sub-pack: the map tiles and what goes with them.

    tile/<XX_YY>.glb    every map tile scene (Map_XX_YY), exported whole by
                        UnityPackFF: props, terrain (shifts applied, splat and
                        control maps, lightmap and grass in the material's
                        extras), animated props with their animation clips, lights,
                        each node's scripts and their fields (effects, the
                        Infected Zones' platforms and waypoints), and the
                        scene's fog and colours in its extras; at its world
                        position
    effect/<name>.glb   the effect prefabs the tiles' effect scripts place
                        (EffectEmitterController.nifObject: the Infected
                        Zones' barriers), named by the prefab, lower case
    shared/             images and mesh data, named by their content
    attr/<XX_YY>.bin    the tile's MapAttributeTable, 129 x 129 bytes
    sky/<set>/skybox_<side>tex.png  the two skyboxes
    bgm/<file>.ogg      the music and ambient tracks

The manifest lists the tiles, the effects, the music and ambient zones
(MusicDataStorage) and the main directional light. Nothing is rendered."""

import hashlib
import json
import math
import os
import re

from unitypack.gltf import TERRAIN_COLLIDER, ExternalFiles, GLTFWriter, mirror_position
from unitypack.mapdata import ATTRIBUTE_HEAL, ATTRIBUTE_POISON, map_attributes, music_zones

from ..client import Client
from ..pack import safe
from .common import AUDIO_CLIP, MAIN, MATERIAL, basename, find, progress, texture_png, write_bytes
from .prefabs import GENERATOR, glb_bytes, write_glb

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


def tiles(build, only=None):
    """The build's map tile archives, or only those whose XX_YY is in only."""
    return sorted(a for a in build.archives()
                  if TILE.match(a) and (not only or "_".join(TILE.match(a).groups()) in only))


def check_partial(final, only):
    """Raises if writing a world pack of only some tiles would replace a
    complete one at final: a reader takes a missing tile for open sea."""
    if not only:
        return
    try:
        with open(os.path.join(final, "manifest.json")) as f:
            partial = json.load(f).get("partial", False)
    except FileNotFoundError:
        return
    if not partial:
        raise RuntimeError(f"{final} holds every tile; a pack of only {', '.join(sorted(only))} would replace it. "
                           "Write it to another directory")


def effect_name(prefab_name):
    "The file an effect prefab goes to: effect/<name>.glb"
    return safe(prefab_name.lower())


def export_effects(asset, out, shared):
    """The prefabs the scene's effect scripts (EffectEmitterController.
    nifObject) place, each written once per content as
    effect/<name>.<hash>.glb (several tiles' processes write side by side;
    choose_effects() keeps one): {name: {"prefab", "path", "hash"}}."""
    found = {}
    for obj in asset.objects.values():
        if obj.type_id >= 0:
            continue
        try:
            fields = obj.read()
        except Exception:
            continue
        fields = getattr(fields, "_obj", fields)
        if not hasattr(fields, "get") or "effectName" not in fields or not fields.get("nifObject"):
            continue
        ptr = fields["nifObject"]
        try:
            prefab = ptr.resolve()
        except Exception:
            continue
        name = effect_name(prefab.name)
        if name in found:
            continue
        w = GLTFWriter(generator=GENERATOR, external=ExternalFiles(shared))
        w.add_gameobject(prefab, scripts=True)
        folder = os.path.join(out, "effect")
        data = glb_bytes(w, folder)
        digest = hashlib.sha256(data).hexdigest()[:16]
        path = os.path.join(folder, f"{name}.{digest}.glb")
        if not os.path.exists(path):
            write_bytes(path, data)
        found[name] = {"prefab": prefab.name, "path": w.container_path(ptr), "hash": digest}
    return found


def choose_effects(out, by_tile):
    """One file per effect name, from the first tile (in name order) that
    places it: effect/<name>.<hash>.glb becomes effect/<name>.glb, the other
    copies go. Returns the manifest's effects and the names whose copies
    differ: 728 keeps a copy in each tile's own sharedAssets, compressed on
    its own, so their normals and texture coordinates differ a little."""
    chosen, copies = {}, {}
    for tile in sorted(by_tile):
        for name, e in by_tile[tile].items():
            chosen.setdefault(name, dict(e, tile=tile))
            copies.setdefault(name, {}).setdefault(e["hash"], []).append(tile)
    folder = os.path.join(out, "effect")
    effects, differing = {}, []
    for name in sorted(chosen):
        e = chosen[name]
        os.replace(os.path.join(folder, f"{name}.{e['hash']}.glb"), os.path.join(folder, f"{name}.glb"))
        for digest in copies[name]:
            if digest != e["hash"]:
                os.remove(os.path.join(folder, f"{name}.{digest}.glb"))
        effects[name] = {"file": f"effect/{name}.glb", "prefab": e["prefab"], "path": e["path"]}
        if len(copies[name]) > 1:
            effects[name]["copies"] = len(copies[name])
            differing.append(name)
    return effects, differing


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
        w.add_scene(asset, scripts=True)
        write_glb(w, os.path.join(out, "tile", f"{tile}.glb"))
        info = {"terrain": any(o.type_id == TERRAIN_COLLIDER for o in asset.objects.values())}
        effects = export_effects(asset, out, shared)
        if effects:
            info["effects"] = effects
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


def export_tiles(client, staging, options):
    import multiprocessing

    jobs = options.jobs
    tasks = [(a, staging.dir, staging.path("shared")) for a in tiles(client.build, options.tiles)]
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
    def archives(build, options):
        return tiles(build, options.tiles)

    @staticmethod
    def check(final, options):
        check_partial(final, options.tiles)

    @staticmethod
    def run(client, staging, archives, options):
        found = export_tiles(client, staging, options)
        exported = {t: i for t, i in found.items() if "error" not in i}
        skipped = {t: i["error"] for t, i in found.items() if "error" in i}
        effects, differing = choose_effects(staging.dir, {t: i.pop("effects", {}) for t, i in exported.items()})
        if differing:
            client.log(f"  {len(differing)} effects have tiles with differing copies ({', '.join(differing)}); "
                       "kept the first tile's")

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
            partial=bool(options.tiles),
            tiles=exported,
            skipped=skipped,
            effects=effects,
            sky={"sets": skies(client, archives, staging), "fusion_rects": FUSION_RECTS},
            light=light(client),
            tracks=sorted(tracks),
            **music,
        )
        poison = sum(1 for i in exported.values() if i.get("attributes", {}).get("poison"))
        return (f"{len(exported)} tiles ({len(skipped)} unreadable, {poison} with poison), {len(effects)} effects, "
                f"{len(tracks)} tracks, {len(music['music'])} music and {len(music['ambient'])} ambient zones")
