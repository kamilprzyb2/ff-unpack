"""The world stage's own logic: effect files, --tiles and partial packs."""

import json
import os

import pytest

from ff_unpack.stages import options, world


def test_effect_name():
    assert world.effect_name("EPbarrier1") == "epbarrier1"
    assert world.effect_name("x_com_GG") == "x_com_gg"


class FakeBuild:
    def archives(self):
        return ["Map_04_05.unity3d", "Map_04_02.unity3d", "Map_04_05.unity3d.extra", "TableData.resourceFile"]


def test_tiles_only():
    assert world.tiles(FakeBuild()) == ["Map_04_02.unity3d", "Map_04_05.unity3d"]
    assert world.tiles(FakeBuild(), {"04_05"}) == ["Map_04_05.unity3d"]
    assert world.World.archives(FakeBuild(), options(tiles=["04_05"])) == ["Map_04_05.unity3d"]
    assert world.World.archives(FakeBuild(), options()) == ["Map_04_02.unity3d", "Map_04_05.unity3d"]


def test_partial_pack_never_replaces_a_whole_one(tmp_path):
    final = tmp_path / "world"
    # nothing there yet, or a partial pack: fine
    world.check_partial(str(final), {"04_05"})
    final.mkdir()
    (final / "manifest.json").write_text(json.dumps({"partial": True}))
    world.check_partial(str(final), {"04_05"})
    # every tile: a pack of some would make the rest look like sea
    (final / "manifest.json").write_text(json.dumps({"partial": False}))
    with pytest.raises(RuntimeError, match="holds every tile"):
        world.check_partial(str(final), {"04_05"})
    # a whole pack may replace anything
    world.check_partial(str(final), None)


def test_choose_effects(tmp_path):
    folder = tmp_path / "effect"
    folder.mkdir()
    for name, digest in (("epbarrier1", "aaaa"), ("epbarrier1", "bbbb"), ("x_com_gg", "cccc")):
        (folder / f"{name}.{digest}.glb").write_bytes(digest.encode())
    by_tile = {
        "04_05": {"epbarrier1": {"prefab": "EPbarrier1", "path": None, "hash": "bbbb"}},
        "04_02": {"epbarrier1": {"prefab": "EPbarrier1", "path": "effect/epbarrier1.nif", "hash": "aaaa"},
                  "x_com_gg": {"prefab": "x_com_gg", "path": None, "hash": "cccc"}},
        "05_05": {"x_com_gg": {"prefab": "x_com_gg", "path": None, "hash": "cccc"}},
    }
    effects, differing = world.choose_effects(str(tmp_path), by_tile)
    # the first tile by name wins, whatever order the processes finished in
    assert effects == {
        "epbarrier1": {"file": "effect/epbarrier1.glb", "prefab": "EPbarrier1", "path": "effect/epbarrier1.nif",
                       "copies": 2},
        "x_com_gg": {"file": "effect/x_com_gg.glb", "prefab": "x_com_gg", "path": None},
    }
    assert sorted(os.listdir(folder)) == ["epbarrier1.glb", "x_com_gg.glb"]
    assert (folder / "epbarrier1.glb").read_bytes() == b"aaaa"
    assert differing == ["epbarrier1"]
