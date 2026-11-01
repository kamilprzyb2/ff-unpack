"""The stages, each writing one sub-pack (PACK_FORMAT.md).

A stage has a name, the sub-pack it writes, the archives it always reads
(`fixed`), a `seed(entry)` that picks the container entries it exports (the
archives holding them are pinned per build in archives.json, see
tools/plan_archives.py), and `run(client, staging, archives, options)`, which
writes the files and the manifest's own fields and returns a summary.
`options` has `jobs` (processes to use) and `tiles` (stage world: only
these XX_YY, or None for all). A stage may also name archives of its own
with `archives(build, options)`."""

from types import SimpleNamespace

from .areas import Areas
from .avatar import Avatar
from .icons import Icons
from .map import Map
from .media import Media
from .models import Models
from .world import World

STAGES = {s.name: s for s in (Areas, Icons, Map, Avatar, Models, Media, World)}


def options(jobs=2, tiles=None):
    return SimpleNamespace(jobs=max(1, jobs), tiles=set(tiles) if tiles else None)
