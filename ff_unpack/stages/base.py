"""The `base` sub-pack: the client's named areas, and its icons.

Stage `areas` writes only the data (it needs nothing but TableData), stage
`base` the icons too."""

from .common import TABLEDATA, TEXTURE_2D, basename, find, script_rows, texture_png, write_bytes
from ..pack import safe, write_json

SUBPACK = "base"


def is_icon(e):
    return e.path.startswith("icons/") and e.class_id == TEXTURE_2D


def areas(client):
    """worldname.asset's rectangles (m_pWorldNameData), the empty ones left
    out: the client names a position by the first that contains it."""
    entry = next(e for e in client.entries(TABLEDATA) if e.path == "worldname.asset")
    out = []
    for i, row in enumerate(script_rows(client.object(entry), "m_pWorldNameData")):
        a = row["Area"]
        if a["width"] <= 0 or a["height"] <= 0:
            continue
        out.append({
            "index": i,
            "name": row["DongName"].strip(),
            "zone": row["ZoneName"].strip(),
            "x": a["x"], "y": a["y"], "width": a["width"], "height": a["height"],
        })
    return out


def write_areas(client, staging):
    rows = areas(client)
    write_json(staging.path("areas.json"), rows, compact=False)
    staging.manifest.update(areas=len(rows), icons=None)
    return rows


def write_icons(client, staging, archives):
    icons, skipped = [], []
    for e in sorted(find(client, archives, is_icon), key=lambda e: e.path):
        name = safe(basename(e.path)) + ".png"
        data = texture_png(client.object(e).read())
        if data is None:
            skipped.append(e.path)
            continue
        write_bytes(staging.path("icons", name), data)
        icons.append(name)
    staging.manifest["icons"] = icons
    return icons, skipped


class Areas:
    name = "areas"
    subpack = SUBPACK
    fixed = [TABLEDATA]

    @staticmethod
    def seed(entry):
        return False

    @staticmethod
    def run(client, staging, archives, jobs):
        rows = write_areas(client, staging)
        return f"{len(rows)} areas"


class Base:
    name = "base"
    subpack = SUBPACK
    fixed = [TABLEDATA]
    seed = staticmethod(is_icon)

    @staticmethod
    def run(client, staging, archives, jobs):
        rows = write_areas(client, staging)
        icons, skipped = write_icons(client, staging, archives)
        for path in skipped:
            client.log(f"  warning: {path} has no image")
        return f"{len(rows)} areas, {len(icons)} icons"
