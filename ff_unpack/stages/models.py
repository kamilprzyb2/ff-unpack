"""The `models` sub-pack: every mob, NPC and nano prefab.

The client loads NPCs, mobs, shinies and the bus as mob/<model>.kfm and
nanos as nano/<model>.kfm (NpcMoveController, NanoMoveController), from
whichever archive the area it's in brought along. Each is exported once,
with every clip, once per set of textures the XDT puts on it; plus every
texture the XDT names for them, and the XDT tables that map NPCs and nanos
to prefabs."""

import re

from unitypack.gltf import ExternalFiles
from unitypack.xdttextures import texture_swaps

from ..pack import safe, write_json
from .common import GAME_OBJECT, TABLEDATA, TRANSFORM, find, png, tables, xdt
from .prefabs import Job, Textures, export_all, is_texture

SUBPACK = "models"
PREFAB = re.compile(r"^(mob|nano)/(.+)\.kfm$")
PREFABS = (GAME_OBJECT, TRANSFORM)
# Where a prefab that several archives hold is taken from: the shared ones
# before the per-tile DongResources (the copies are the same prefab).
PREFERRED = ("World_shared", "Freearea", "TrainingGrounds", "Tutorial", "Nano", "FutureNano", "CharacterCreation")
TABLES = {
    "m_pNpcTable": ("m_pNpcData", "m_pNpcMeshData"),
    "m_pNanoTable": ("m_pNanoData", "m_pNanoMeshData"),
    "m_pShinyTable": ("m_pShinyData", "m_pShinyMeshData"),
    "m_pTransportationTable": ("m_pTransportationData", "m_pTransportationMeshData"),
    "m_pAnimationTable": ("m_pNpcData", "m_pNanoData"),
}


def preferred(archives):
    def rank(a):
        return next((i for i, p in enumerate(PREFERRED) if a.startswith(p)), len(PREFERRED)), a

    return sorted(archives, key=rank)


def is_prefab(e):
    return e.class_id in PREFABS and PREFAB.match(e.path)


class Models:
    name = "models"
    subpack = SUBPACK
    fixed = [TABLEDATA]

    @staticmethod
    def seed(e):
        return is_prefab(e) or is_texture(e)

    @staticmethod
    def run(client, staging, archives, options):
        archives = preferred(archives)
        table = xdt(client)
        tasks = []
        for e in find(client, archives, is_prefab):
            kind, model = PREFAB.match(e.path).groups()
            tasks.append((e, f"{kind}/{safe(model)}"))
        job = Job(client.build.protocol, client.cache, archives, staging.path("shared"), staging.dir,
                  actor_bones=False, as_worn=False)
        results = export_all(client, job, tasks, options.jobs, "prefabs")
        prefabs = {"mob": {}, "nano": {}}
        for path, r in sorted(results.items()):
            kind, model = PREFAB.match(path).groups()
            prefabs[kind][model] = r
        failed = sorted(p for p, r in results.items() if "error" in r)

        write_json(staging.path("tables.json"), tables(table, TABLES))
        index = Textures(client, archives)
        shared = ExternalFiles(staging.path("shared"))
        names = sorted({t.lower() for (folder, _), sets in texture_swaps(table).items() if folder in ("mob", "nano")
                        for s in sets for t in (s.main, s.sub) if t})
        textures, missing = {}, []
        for name in names:
            tex = index.get(name)
            image = tex.image if tex is not None else None
            if image is None:
                missing.append(name)
                continue
            textures[name] = "shared/" + shared.put(png(image), "png")
        write_json(staging.path("textures.json"), textures, compact=False)

        staging.manifest.update(mob=prefabs["mob"], nano=prefabs["nano"], textures=len(textures),
                                missing_textures=missing, failed=failed)
        clips = sum(len(r.get("clips", {})) for k in prefabs.values() for r in k.values())
        return (f"{len(prefabs['mob'])} mob and {len(prefabs['nano'])} nano prefabs ({clips} clips), "
                f"{len(textures)} textures ({len(missing)} named but missing), {len(failed)} failed")
