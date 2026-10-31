"""The world stage's own logic: effect file names and --tiles."""

from ff_unpack.stages import world


def test_effect_name():
    assert world.effect_name("EPbarrier1") == "epbarrier1"
    assert world.effect_name("x_com_GG") == "x_com_gg"


class FakeBuild:
    def archives(self):
        return ["Map_04_05.unity3d", "Map_04_02.unity3d", "Map_04_05.unity3d.extra", "TableData.resourceFile"]


def test_tiles_only():
    try:
        assert world.tiles(FakeBuild()) == ["Map_04_02.unity3d", "Map_04_05.unity3d"]
        world.ONLY.add("04_05")
        assert world.tiles(FakeBuild()) == ["Map_04_05.unity3d"]
    finally:
        world.ONLY.clear()
