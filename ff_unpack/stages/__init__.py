"""The stages, each writing one sub-pack (PACK_FORMAT.md).

A stage has a name, the sub-pack it writes, the archives it always reads
(`fixed`), a `seed(entry)` that picks the container entries it exports (the
archives holding them are pinned per build in archives.json, see
tools/plan_archives.py), and `run(client, staging, archives, jobs)`, which
writes the files and the manifest's own fields and returns a summary."""

from .base import Areas, Base

STAGES = {s.name: s for s in (Areas, Base)}
