"""The `avatar` sub-pack: what a player character is built from.

The boy and girl actors (actor/m.kfm, actor/w.kfm) with every clip and the
bone table worn items bind to; everything players wear (wear/*.nif) with
the textures the XDT gives it, worn items with their skinned meshes only;
the skin and hair colour palettes (male.bsd); the human NPCs' looks
(all_hnpc.asset); the chat menu's emote icons; every texture the XDT and
the human NPCs name; and the XDT tables a character builder reads."""

import re

from unitypack.gltf import ExternalFiles
from unitypack.xdttextures import texture_swaps

from ..pack import safe, write_json
from .common import (GAME_OBJECT, MAIN, TABLEDATA, TEXTURE_2D, TRANSFORM, find, png, script_rows,
                     tables, texture_png, to_json, write_bytes, xdt)
from .prefabs import Job, Textures, export_all, is_texture

SUBPACK = "avatar"
ACTOR = re.compile(r"^actor/([mw])\.kfm$")
WEAR = re.compile(r"^wear/(.+)\.nif$")
EMOTE = re.compile(r"(^|/)(ui_)?emotechaticon/([^/]+)\.png$")
# The XDT tables a character builder reads (item → model and textures,
# human NPCs, animations and emotes by id).
TABLES = {
    "m_pShirtsItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pPantsItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pShoesItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pHatItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pGlassItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pBackItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pWeaponItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pVehicleItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pFaceItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pHeadItemTable": ("m_pItemData", "m_pItemMeshData"),
    "m_pNpcTable": ("m_pNpcData", "m_pNpcMeshData"),
    "m_pAvatarTable": ("m_pAvatarData", "m_pAvatarGrowData"),
    "m_pAnimationTable": ("m_pAvatarData",),
    "m_pEmoteTable": ("m_pEmoteAnimationData", "m_pEmoteTextureData"),
}
PREFABS = (GAME_OBJECT, TRANSFORM)


def preferred(archives):
    """CharacterSelection first: CharacterCreation repeats some of its
    prefabs (the starting clothes)."""
    return sorted(archives, key=lambda a: (not a.startswith("CharacterSelection"), a))


def is_prefab(e):
    return e.class_id in PREFABS and bool(ACTOR.match(e.path) or WEAR.match(e.path))


def seed(e):
    return (
        is_prefab(e)
        # the nano archives hold only nanos' skins, never worn
        or (is_texture(e) and "nano" not in e.archive.lower())
        or (EMOTE.search(e.path) and e.class_id == TEXTURE_2D)
    )


def palettes(client):
    """male.bsd: the skin and hair colours (in TableData from 728 on, in
    main.unity3d before), found by its fields."""
    from unitypack.mapdata import script_objects

    for name in client.files(TABLEDATA) + client.files(MAIN):
        found = next(script_objects(client.asset(name), "cSkinColor", "cHairColor"), None)
        if found is not None:
            return {
                "skin": to_json(found["cSkinColor"]["skinColor"]),
                "hair": to_json(found["cHairColor"]["hairColor"]),
            }
    raise RuntimeError("no male.bsd colour palettes in TableData or main.unity3d")


def hnpc_rows(client):
    entry = next((e for e in client.entries(TABLEDATA) if e.path == "all_hnpc.asset"), None)
    return script_rows(client.object(entry), "TableElement") if entry else None


def named_textures(table, hnpc):
    """Every texture the XDT puts on something players wear, and every one a
    human NPC names."""
    names = set()
    for (folder, _), sets in texture_swaps(table).items():
        if folder == "wear":
            for s in sets:
                names.update(t for t in (s.main, s.sub) if t)
    for row in hnpc or ():
        for k, v in row.items():
            if k.startswith("str") and "Texture" in k and v and v.lower() != "null":
                names.add(v.rsplit(".", 1)[0])
    return {n.lower() for n in names}


class Avatar:
    name = "avatar"
    subpack = SUBPACK
    fixed = [TABLEDATA, MAIN]
    seed = staticmethod(seed)

    @staticmethod
    def run(client, staging, archives, jobs):
        archives = preferred(archives)
        table = xdt(client)
        hnpc = hnpc_rows(client)

        tasks = []
        for e in find(client, archives, is_prefab):
            m = ACTOR.match(e.path)
            tasks.append((e, f"actor/{m.group(1)}" if m else f"wear/{safe(WEAR.match(e.path).group(1))}"))
        job = Job(client.build.protocol, client.cache, archives, staging.path("shared"), staging.dir,
                  actor_bones=True, as_worn=True)
        results = export_all(client, job, tasks, jobs, "prefabs")
        actors = {g: results[f"actor/{g}.kfm"] for g in "mw" if f"actor/{g}.kfm" in results}
        wear = {WEAR.match(p).group(1): r for p, r in sorted(results.items()) if WEAR.match(p)}
        failed = sorted(p for p, r in results.items() if "error" in r)
        if set(actors) != {"m", "w"}:
            raise RuntimeError("the boy or girl actor is missing")

        write_json(staging.path("palettes.json"), palettes(client), compact=False)
        if hnpc is not None:
            write_json(staging.path("hnpc.json"), hnpc)
        write_json(staging.path("tables.json"), tables(table, TABLES))

        emotes = []
        for e in find(client, archives, lambda e: EMOTE.search(e.path) and e.class_id == TEXTURE_2D):
            name = safe(EMOTE.search(e.path).group(3))
            write_bytes(staging.path("emote", f"{name}.png"), texture_png(client.object(e).read()))
            emotes.append(name)

        # Textures by the names the XDT uses, in shared/ like the models'.
        index = Textures(client, archives)
        shared = ExternalFiles(staging.path("shared"))
        textures, missing = {}, []
        for name in sorted(named_textures(table, hnpc)):
            tex = index.get(name)
            image = tex.image if tex is not None else None
            if image is None:
                missing.append(name)
                continue
            textures[name] = "shared/" + shared.put(png(image), "png")
        write_json(staging.path("textures.json"), textures, compact=False)

        staging.manifest.update(
            actors=actors,
            wear=wear,
            emotes=sorted(emotes),
            hnpc=len(hnpc) if hnpc is not None else None,
            textures=len(textures),
            missing_textures=missing,
            failed=failed,
        )
        clips = sum(len(r.get("clips", {})) for r in actors.values())
        return (f"2 actors ({clips} clips), {len(wear)} wearables, {len(textures)} textures "
                f"({len(missing)} named but missing), {len(emotes)} emotes, {len(failed)} failed")
