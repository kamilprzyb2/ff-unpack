"""The `icons` sub-pack: every texture in an icons/ folder of the client,
as <name>.png, named as the client names it."""

from ..pack import safe
from .common import TEXTURE_2D, basename, find, texture_png, write_bytes

SUBPACK = "icons"


def is_icon(e):
    return e.path.startswith("icons/") and e.class_id == TEXTURE_2D


class Icons:
    name = "icons"
    subpack = SUBPACK
    fixed = []
    seed = staticmethod(is_icon)

    @staticmethod
    def run(client, staging, archives, options):
        icons = []
        for e in sorted(find(client, archives, is_icon), key=lambda e: e.path):
            name = safe(basename(e.path)) + ".png"
            data = texture_png(client.object(e).read())
            if data is None:
                client.log(f"  warning: {e.path} has no image")
                continue
            write_bytes(staging.path(name), data)
            icons.append(name)
        staging.manifest["icons"] = icons
        return f"{len(icons)} icons"
