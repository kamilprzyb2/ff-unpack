"""Each stage on a real client build: what the manifests say, compared with
tests/expected/, and that the packs hold together."""

import json
import os
import random
import struct
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

VALIDATOR = os.environ.get("FF_UNPACK_GLTF_VALIDATOR")


def manifest(folder):
    return json.loads((folder / "manifest.json").read_text())


def glb_json(path):
    data = path.read_bytes()
    assert data[:4] == b"glTF" and struct.unpack("<I", data[4:8])[0] == 2
    n = struct.unpack("<I", data[12:16])[0]
    # a BIN chunk, which VTK's reader (F3D) insists on
    assert data[24 + n:28 + n] == b"BIN\0", f"{path}: no BIN chunk"
    return json.loads(data[20:20 + n])


def check_uris(path):
    """Every image and buffer a .glb points to is there."""
    doc = glb_json(path)
    for item in doc.get("images", []) + doc.get("buffers", []):
        if "uri" in item:
            assert (path.parent / item["uri"]).is_file(), f"{path}: {item['uri']}"
    return doc


def validate(paths):
    """The Khronos glTF validator on the files, when FF_UNPACK_GLTF_VALIDATOR
    names a directory with node_modules/gltf-validator."""
    if not VALIDATOR:
        return
    script = Path(__file__).with_name("validate.mjs")
    out = subprocess.run(["node", str(script), VALIDATOR, *map(str, paths)], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def sample(items, n, seed=0):
    items = sorted(items)
    return random.Random(seed).sample(items, min(n, len(items)))


def check_header(m, folder, packs, subpack):
    assert m["format"] == f"ff-unpack/{subpack}"
    assert m["format_version"] == 1
    assert m["build"]["name"] == packs.build.name == folder.parent.name
    archives = packs.build.archives()
    for archive, sha in m["sources"].items():
        assert archives[archive][1]["hash"] == sha


def prefab_files(folder, prefabs):
    """Every file the manifest lists for some prefabs is there; returns them."""
    files = []
    for r in prefabs.values():
        assert "error" not in r, r
        for v in r["variants"].values():
            files.append(folder / v["file"])
        files += [folder / f for f in r.get("clips", {}).values()]
    missing = [f for f in files if not f.is_file()]
    assert not missing, missing[:5]
    return files


def test_areas(packs, expected):
    folder = packs("areas")
    m = manifest(folder)
    check_header(m, folder, packs, "areas")
    areas = json.loads((folder / "areas.json").read_text())
    assert m["areas"] == len(areas)
    assert m["sources"].keys() == {"TableData.resourceFile"}
    for a in areas:
        assert a["name"] and a["width"] > 0 and a["height"] > 0
        assert 0 <= a["x"] < 16 * 512 and 0 <= a["y"] < 16 * 512
    expected.check("areas", {"areas": len(areas)})


def test_icons(packs, expected):
    folder = packs("icons")
    m = manifest(folder)
    check_header(m, folder, packs, "icons")
    icons = sorted(p.name for p in folder.iterdir() if p.name != "manifest.json")
    assert icons == sorted(m["icons"])
    prefixes = sorted({i.rsplit("_", 1)[0] for i in icons})
    expected.check("icons", {"icons": len(icons), "icon_families": prefixes})


def test_map(packs, expected):
    folder = packs("map")
    m = manifest(folder)
    check_header(m, folder, packs, "map")
    images = sorted(p.name for p in folder.iterdir() if p.name != "manifest.json")
    listed = {lv["file"] for lv in m["world"]}
    listed |= {lv["file"] for z in m["zones"].values() for lv in z["levels"]}
    listed |= {s["file"] for s in m["minimap"]["sheets"]} | {m["minimap"]["all"]}
    assert images == sorted(listed)
    # the sheets tile the map
    assert sum(s["rect"][2] * s["rect"][3] for s in m["minimap"]["sheets"]) == m["size"] ** 2
    for z in m["zones"].values():
        x, y, w, h = z["rect"]
        assert 0 <= x and x + w <= m["size"] and 0 <= y and y + h <= m["size"]
    expected.check("map", {
        "world": len(m["world"]),
        "zones": {k: len(z["levels"]) for k, z in m["zones"].items()},
        "sheets": len(m["minimap"]["sheets"]),
        "images": len(images),
    })


def test_avatar(packs, expected):
    folder = packs("avatar")
    m = manifest(folder)
    check_header(m, folder, packs, "avatar")
    assert not m["failed"]
    files = prefab_files(folder, {**m["actors"], **m["wear"]})
    # the actors carry the bone table worn items bind to
    for g in "mw":
        doc = check_uris(folder / m["actors"][g]["variants"]["default"]["file"])
        assert any("actor_bones" in n.get("extras", {}) for n in doc["nodes"])
    # every worn skinned item binds to it
    unbound = [k for k, r in m["wear"].items() for w in r.get("warnings", []) if "ActorWearIndexTable" in w]
    palettes = json.loads((folder / "palettes.json").read_text())
    hnpc = json.loads((folder / "hnpc.json").read_text())
    textures = json.loads((folder / "textures.json").read_text())
    assert all((folder / f).is_file() for f in textures.values())
    tables = json.loads((folder / "tables.json").read_text())
    picked = sample(files, 40)
    for f in picked:
        check_uris(f)
    validate(picked)
    expected.check("avatar", {
        "actor_clips": {g: len(m["actors"][g]["clips"]) for g in "mw"},
        "wear": len(m["wear"]),
        "wear_variants": sum(len(r["variants"]) for r in m["wear"].values()),
        "wear_with_clips": sum(1 for r in m["wear"].values() if "clips" in r),
        "left_out": sum(r.get("left_out", 0) for r in m["wear"].values()),
        "unbound": len(unbound),
        "palettes": [len(palettes["skin"]), len(palettes["hair"])],
        "hnpc": len(hnpc),
        "emotes": len(m["emotes"]),
        "textures": len(textures),
        "missing_textures": len(m["missing_textures"]),
        "tables": sorted(tables),
    })


def test_models(packs, expected):
    folder = packs("models")
    m = manifest(folder)
    check_header(m, folder, packs, "models")
    assert not m["failed"]
    files = prefab_files(folder, {**m["mob"], **m["nano"]})
    textures = json.loads((folder / "textures.json").read_text())
    assert all((folder / f).is_file() for f in textures.values())
    picked = sample(files, 40)
    for f in picked:
        check_uris(f)
    validate(picked)
    expected.check("models", {
        "mob": len(m["mob"]),
        "nano": len(m["nano"]),
        "variants": sum(len(r["variants"]) for k in ("mob", "nano") for r in m[k].values()),
        "clips": sum(len(r.get("clips", {})) for k in ("mob", "nano") for r in m[k].values()),
        "textures": len(textures),
        "missing_textures": len(m["missing_textures"]),
    })


def test_media(packs, expected):
    folder = packs("media")
    m = manifest(folder)
    check_header(m, folder, packs, "media")
    for line in [f"vo/{s}_{line}" for s, lines in m["voices"].items() for line in lines]:
        assert (folder / f"{line}.ogg").is_file()
    for f in [f for clips in m["nanos"].values() for fs in clips.values() for f in fs]:
        assert (folder / "nano" / f"{f}.ogg").is_file()
    for f in (folder / "nano").iterdir():
        assert f.read_bytes()[:4] == b"OggS"
    for zone, panels in m["backdrops"].items():
        assert panels == list(range(1, 11)), zone
    expected.check("media", {
        "speakers": len(m["voices"]),
        "voices": sum(len(v) for v in m["voices"].values()),
        "story": len(m["story"]),
        "hints": len(m["hints"]),
        "nanos_with_events": len(m["nanos"]),
        "nano_event_lines": len({f for c in m["nanos"].values() for fs in c.values() for f in fs}),
        "dismiss": sum(len(v) for v in m["dismiss"].values()),
        "nano_voices": len(m["nano_voices"]),
        "ep": [len(m["ep"]["big"]), len(m["ep"]["small"])],
        "backdrops": sorted(m["backdrops"]),
        "help": len(m["help"]),
    })


def test_world(packs, expected):
    folder = packs("world")
    m = manifest(folder)
    check_header(m, folder, packs, "world")
    for tile, info in m["tiles"].items():
        assert (folder / "tile" / f"{tile}.glb").is_file()
        if "attributes" in info:
            assert (folder / "attr" / f"{tile}.bin").stat().st_size == info["attributes"]["size"] ** 2
    for s in m["sky"]["sets"]:
        assert len(list((folder / "sky" / s).iterdir())) == 6
    for z in m["music"] + m["ambient"]:
        assert z["file"] is None or (folder / "bgm" / z["file"]).is_file()
    # tiles keep their world position: the scene root is at -x·512, z·512
    doc = check_uris(folder / "tile" / "04_02.glb")
    root = doc["nodes"][doc["scenes"][0]["nodes"][0]]
    assert root["translation"] == [-4 * 512.0, 0.0, 2 * 512.0]
    assert m["partial"] is False
    effects = m["effects"]
    for name, e in effects.items():
        assert e["file"] == f"effect/{name}.glb"
        check_uris(folder / e["file"])
    assert sorted(p.name for p in (folder / "effect").iterdir()) == sorted(f"{n}.glb" for n in effects)
    picked = [folder / "tile" / f"{t}.glb" for t in sample(m["tiles"], 3)]
    picked += [folder / e["file"] for e in effects.values()]
    for f in picked:
        check_uris(f)
    validate(picked)
    expected.check("world", {
        "tiles": len(m["tiles"]),
        "skipped": len(m["skipped"]),
        "terrain": sum(1 for i in m["tiles"].values() if i["terrain"]),
        "poison": sum(1 for i in m["tiles"].values() if i.get("attributes", {}).get("poison")),
        "heal": sum(1 for i in m["tiles"].values() if i.get("attributes", {}).get("heal")),
        "sky": m["sky"]["sets"],
        "light": m["light"],
        "effects": sorted(effects),
        "effects_with_copies": sorted(n for n, e in effects.items() if "copies" in e),
        "tracks": len(m["tracks"]),
        "music": len(m["music"]),
        "ambient": len(m["ambient"]),
    })
