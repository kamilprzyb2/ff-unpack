"""Making clip documents smaller before they're written.

UnityPackFF samples every curve of a clip at the clip's rate, so a bone that
never moves still gets a keyframe per frame. More than half the tracks of
the client's clips are like that. A glTF sampler with one keyframe holds
that value for the whole clip, so such a track is cut to its first
keyframe: the same animation, in about a quarter fewer bytes (104's
creature clips: 417 MB before, 309 MB after)."""

import struct

FLOAT = 5126
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _read(doc, data, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    n = acc["count"] * COMPONENTS[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return list(struct.unpack_from(f"<{n}f", data, start))


def _tracks(doc):
    """The float curve tracks in extras ({"input", "output", ...})."""
    for clip in doc.get("animations", []):
        yield from clip.get("extras", {}).get("float_curves", {}).values()
    for clip in doc.get("extras", {}).get("material_clips", []):
        yield from clip.get("float_curves", {}).values()


def compact(writer):
    """Cuts the constant tracks of a clip-only GLTFWriter (as split_clips()
    gives them: animations, no meshes, every accessor a float in the BIN
    chunk) to one keyframe, and repacks its buffer. Anything else is left
    as it is."""
    doc = writer.json
    if any(k in doc for k in ("meshes", "skins", "images")) or getattr(writer, "_buffers", None):
        return writer
    accessors = doc.get("accessors", [])
    if not accessors or any(a["componentType"] != FLOAT or a.get("sparse") for a in accessors):
        return writer
    data = bytes(writer.bin)
    values = {}  # accessor -> (type, floats)

    def value(i):
        if i not in values:
            values[i] = (accessors[i]["type"], _read(doc, data, i))
        return values[i][1]

    new = []  # the accessors after compacting: (type, floats)
    seen = {}  # (type, floats) -> index in new: equal accessors are written once
    remap = {}

    def add(typ, floats):
        key = (typ, tuple(floats))
        if key not in seen:
            seen[key] = len(new)
            new.append((typ, floats))
        return seen[key]

    def keep(i):
        if i not in remap:
            remap[i] = add(accessors[i]["type"], value(i))
        return remap[i]

    for clip in doc.get("animations", []):
        for s in clip["samplers"]:
            out, typ = value(s["output"]), accessors[s["output"]]["type"]
            n = COMPONENTS[typ]
            first = out[:n]
            if s.get("interpolation", "LINEAR") != "CUBICSPLINE" and len(out) > n and all(
                out[k] == first[k % n] for k in range(len(out))
            ):
                s["input"] = add("SCALAR", value(s["input"])[:1])
                s["output"] = add(typ, first)
            else:
                s["input"], s["output"] = keep(s["input"]), keep(s["output"])
    for track in _tracks(doc):
        for k in ("input", "output"):
            if k in track:
                track[k] = keep(track[k])

    # One buffer view holds them all, each accessor at its offset.
    blob = bytearray()
    accs = []
    for typ, floats in new:
        n = COMPONENTS[typ]
        acc = {"bufferView": 0, "byteOffset": len(blob), "componentType": FLOAT, "count": len(floats) // n, "type": typ}
        blob += struct.pack(f"<{len(floats)}f", *floats)
        accs.append(acc)
    # Animation inputs must have min and max.
    for i in {s["input"] for clip in doc.get("animations", []) for s in clip["samplers"]}:
        floats = new[i][1]
        accs[i]["min"], accs[i]["max"] = [min(floats)], [max(floats)]
    doc["accessors"] = accs
    doc["bufferViews"] = [{"buffer": 0, "byteLength": len(blob)}]
    writer.bin = blob
    return writer
