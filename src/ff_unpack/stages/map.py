"""The `map` sub-pack: the client's world map and minimap, as it draws them.

    payzone_00N.png     the world map, one image per zoom step (WorldMapMode)
    freezone_00N.png    the Future and the tutorial square's map
    darkland_00N.png    the Dark Lands' map
    all_minimap_NN.png  the NanoCom's minimap, a 4 × 4 grid of sheets
                        (cnGUINanocom)
    all_minimap.png     the whole minimap in one image

Every image covers the whole map, [0, 8192) metres both ways, north up."""

import re

from .common import TEXTURE_2D, basename, find, texture_png, write_bytes

SUBPACK = "map"
SIZE = 8192
NAMES = ([f"payzone_00{i}" for i in range(1, 5)] + ["freezone_001", "freezone_002", "darkland_001", "darkland_002"]
         + ["all_minimap"] + [f"all_minimap_{n:02d}" for n in range(1, 17)])
PATH = re.compile(r"^(tutorialassets|uiassets/ui_map|uiassets/ui_minimap)/([^/]+)\.[a-z]+$")
# Where the client loads them from. In 728 every tile's archive carries a
# copy as well, which isn't needed.
ARCHIVES = {104: ["Tutorial.resourceFile"], 728: ["Tutorial.resourceFile"],
            1013: ["UI_map.resourceFile", "UI_minimap.resourceFile"]}

# WorldMapMode: how much of the map each zoom step shows (fZoomRangeX), and
# the zones that have a map of their own. A zone's map opens at zoom step 3
# (the tutorial's at 4) and stays within the zone's rectangle.
SPANS = [1.0, 0.5, 0.25, 0.1159668]
ZONES = {
    "future": ([5632, 512, 2048, 2048], ["freezone_001", "freezone_002"], 2),
    "darklands": ([1024, 5120, 2560, 2048], ["darkland_001", "darkland_002"], 2),
    "tutorial": ([0, 0, 1536, 1536], ["freezone_002"], 3),
}


def is_map(e):
    m = PATH.match(e.path)
    return e.class_id == TEXTURE_2D and bool(m) and m.group(2) in NAMES


def sheet_rect(n):
    """Minimap sheet n (1-16): the map rectangle it covers. The client draws
    sheet (3 - row) * 4 + column + 1, with row and column counted from the
    map's south-west corner in quarters."""
    col, row = (n - 1) % 4, 3 - (n - 1) // 4
    q = SIZE // 4
    return [col * q, row * q, q, q]


def levels(names, first, have):
    return [{"file": f"{n}.png", "span": SPANS[first + i]} for i, n in enumerate(names) if n in have]


class Map:
    name = "map"
    subpack = SUBPACK
    fixed = []

    @staticmethod
    def seed(entry):
        return False

    @staticmethod
    def archives(build, options):
        return ARCHIVES[build.protocol]

    @staticmethod
    def run(client, staging, archives, options):
        have = set()
        for e in sorted(find(client, archives, is_map), key=lambda e: e.path):
            name = basename(e.path)
            if name in have:
                continue
            data = texture_png(client.object(e).read())
            if data is None:
                client.log(f"  warning: {e.path} has no image")
                continue
            write_bytes(staging.path(f"{name}.png"), data)
            have.add(name)

        staging.manifest.update(
            size=SIZE,
            world=levels(NAMES[:4], 0, have),
            zones={z: {"rect": rect, "levels": levels(names, first, have)}
                   for z, (rect, names, first) in ZONES.items()},
            minimap={
                "all": "all_minimap.png" if "all_minimap" in have else None,
                "sheets": [{"file": f"all_minimap_{n:02d}.png", "rect": sheet_rect(n)}
                           for n in range(1, 17) if f"all_minimap_{n:02d}" in have],
            },
        )
        missing = [n for n in NAMES if n not in have]
        if missing:
            client.log(f"  warning: not in the client: {', '.join(missing)}")
        return f"{len(have)} map images"
