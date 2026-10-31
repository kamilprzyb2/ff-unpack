import struct

from unitypack.gltf import GLTFWriter

from ff_unpack.gltfclip import compact


def clip_writer(tracks, material=None):
    """A clip-only document: one animation, a sampler per track ({path:
    (times, values, type)}) on node 0, plus a float curve in extras."""
    w = GLTFWriter()
    w.json["nodes"] = [{"name": "root"}]
    samplers, channels = [], []
    for i, (path, (times, values, typ)) in enumerate(tracks.items()):
        inp = w.accessor(times, "SCALAR", minmax=True)
        out = w.accessor([c for v in values for c in v], typ)
        samplers.append({"input": inp, "output": out, "interpolation": "LINEAR"})
        channels.append({"sampler": i, "target": {"node": 0, "path": path}})
    anim = {"name": "clip", "samplers": samplers, "channels": channels}
    if material:
        times, values = material
        anim["extras"] = {"float_curves": {"root:_FatFactor": {
            "input": w.accessor(times, "SCALAR"), "output": w.accessor(values, "SCALAR"), "node": 0}}}
    w.json["animations"] = [anim]
    return w


def read(w, index):
    acc = w.json["accessors"][index]
    view = w.json["bufferViews"][acc["bufferView"]]
    n = acc["count"] * {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[acc["type"]]
    return list(struct.unpack_from(f"<{n}f", bytes(w.bin), view.get("byteOffset", 0) + acc.get("byteOffset", 0)))


def test_constant_tracks_keep_one_keyframe():
    times = [0.0, 0.5, 1.0]
    w = clip_writer({
        "rotation": (times, [[0.0, 0.0, 0.0, 1.0]] * 3, "VEC4"),
        "translation": (times, [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 2.0, 0.0]], "VEC3"),
        "scale": (times, [[1.0, 1.0, 1.0]] * 3, "VEC3"),
    }, material=([0.0, 0.5, 1.0], [0.0075, 0.0, -0.0078]))
    before = len(w.glb())
    compact(w)
    s = w.json["animations"][0]["samplers"]
    assert read(w, s[0]["input"]) == [0.0] and read(w, s[0]["output"]) == [0.0, 0.0, 0.0, 1.0]
    assert read(w, s[1]["input"]) == times and read(w, s[1]["output"]) == [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0]
    assert read(w, s[2]["output"]) == [1.0, 1.0, 1.0]
    # equal accessors are stored once: the moving track's times and the
    # float curve's are the same values
    track = w.json["animations"][0]["extras"]["float_curves"]["root:_FatFactor"]
    assert track["input"] == s[1]["input"]
    assert [round(v, 6) for v in read(w, track["output"])] == [0.0075, 0.0, -0.0078]
    # inputs have min and max, as glTF requires
    for sampler in s:
        acc = w.json["accessors"][sampler["input"]]
        assert acc["min"] == [min(read(w, sampler["input"]))] and acc["max"] == [max(read(w, sampler["input"]))]
    assert len(w.json["bufferViews"]) == 1
    assert len(w.glb()) < before


def test_documents_with_geometry_are_left_alone():
    w = clip_writer({"scale": ([0.0, 1.0], [[1.0, 1.0, 1.0]] * 2, "VEC3")})
    w.json["meshes"] = [{"primitives": []}]
    accessors = list(w.json["accessors"])
    compact(w)
    assert w.json["accessors"] == accessors
