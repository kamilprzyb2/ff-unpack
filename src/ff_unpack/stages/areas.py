"""The `areas` sub-pack: the client's named areas, from TableData alone."""

from ..pack import write_json
from .common import TABLEDATA, script_rows

SUBPACK = "areas"


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


class Areas:
    name = "areas"
    subpack = SUBPACK
    fixed = [TABLEDATA]

    @staticmethod
    def seed(entry):
        return False

    @staticmethod
    def run(client, staging, archives, options):
        rows = areas(client)
        write_json(staging.path("areas.json"), rows, compact=False)
        staging.manifest["areas"] = len(rows)
        return f"{len(rows)} areas"
