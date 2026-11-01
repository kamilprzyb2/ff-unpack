# Pack format, version 1

The contract between ff-unpack and everything that reads its output. A reader states which `format_version`s it reads. "Versions" at the end says when the version changes, and lists every change.

## Layout

```
<packs>/
  beta-20100104/        one directory per client build (protocol 104)
    areas/              named areas
    icons/              icons
    map/                the world map and the minimap
    avatar/             player characters
    models/             mobs, NPCs, nanos
    media/              voices and UI art
    world/              map tiles
  beta-20100728/        protocol 728
  beta-20111013/        protocol 1013
```

Each build directory is named after its client build, and the protocol version maps to it: 104 → `beta-20100104`, 728 → `beta-20100728`, 1013 → `beta-20111013`. Each sub-pack is optional and stands alone. ff-unpack writes a sub-pack next to its final place, in a hidden folder (`.<sub-pack>-<random>/`), and renames it into place in one step, so a reader sees the old pack or the new one, never half of one. Readers should skip hidden folders: one is there while ff-unpack runs, or after it was killed.

## Conventions

- **File names** that come from the client are lowercased, and anything but `a-z`, `0-9`, `_`, `.`, `-`, `@` and `+` becomes `_`. For example, `help/buddy_window - tight.jpg` becomes `help/buddy_window_-_tight.jpg`.
- **JSON** is UTF-8. Colours are `[r, g, b, a]` floats from 0 to 1. Values read from the client's tables keep the client's field names (`m_iNpcNumber`, `strHairMesh`).
- **Images** are upright PNGs (row 0 at the top), unless noted otherwise. They are only images that exist in the client: ff-unpack draws nothing and renders nothing.
- **Audio** is Ogg Vorbis, copied byte for byte. Every `.wav` and `.mp3` in the client is an Ogg Vorbis file inside.
- **glTF** files are binary glTF 2.0 (`.glb`), written by UnityPackFF (see "glTF" below).
- **Shared files.** `avatar/`, `models/` and `world/` each have a `shared/` folder. It holds the images (`.png`) and mesh data (`.bin`) that their `.glb` files refer to by relative URI. Each file is named by the first 16 hex digits of the SHA-256 of its content, so a texture or mesh that many models use is stored once.
- **World coordinates.** Unity is left-handed and glTF is right-handed, so UnityPackFF mirrors everything along x: a Unity position `(x, y, z)` is `(-x, y, z)` in glTF. Units are metres (Unity units). The game's network protocol uses centimetres: its `(X, Y, Z)` is Unity `(X / 100, Z / 100, Y / 100)`.

## Manifests

Every sub-pack has a `manifest.json` with these fields, followed by the sub-pack's own fields:

| Field | |
|---|---|
| `format` | `"ff-unpack/<sub-pack>"`, e.g. `"ff-unpack/areas"` |
| `format_version` | `1` |
| `build` | `{"protocol": 104, "name": "beta-20100104", "uuid": "<launcher manifest uuid>"}` |
| `ff_unpack` | ff-unpack's version |
| `unitypackff` | `{"version", "commit", "dirty"}` of the UnityPackFF that exported it: `commit` only when it ran from a git checkout, `dirty: true` when that checkout had uncommitted changes (then the pack is not reproducible from the commit) |
| `created` | when, UTC, ISO 8601 |
| `sources` | `{archive: sha256}` of every client archive read, including the ones read only because something pointed into them |
| `fingerprint` | SHA-256 over `sources` and the exporter (`format_version`, ff-unpack's version, UnityPackFF's commit or version). It is the same whenever the same client files are unpacked by the same tools, and changes when either changes, so **this is what a reader compares** to tell whether what it derived from a pack (renders, caches) is still current. Don't hash `manifest.json` itself: `created` changes on every run |

## areas/

Written by stage `areas`, which reads only the client's TableData.

```
areas/
  manifest.json
  areas.json
```

**`areas.json`**: the client's named areas (TableData `worldname.asset`, `m_pWorldNameData`). The client names a position by the first rectangle that contains it. Empty rows are left out.

```json
[{"index": 1, "name": "Candy Cove", "zone": "The Suburbs", "x": 4096.0, "y": 2560.0, "width": 512.0, "height": 512.0}, ...]
```

`index` is the row in the client's table. `x`, `y`, `width` and `height` are in metres on the map: x east, y north. The world is a 16 × 16 grid of 512 m tiles, so tile `XX_YY` covers `[XX·512, XX·512 + 512) × [YY·512, YY·512 + 512)`. 104 and 728 have 93 areas, 1013 has 96. Manifest field `areas`: how many.

## icons/

```
icons/
  manifest.json
  <name>.png
```

Every texture in an `icons/` folder of the client, named as the client names it (`cosicon_00.png`, `nanoicon_01.png`, `mobicon_12.png`). The XDT's icon tables give an item, nano or NPC's icon number. Manifest field `icons`: the file names.

## map/

The client's world map (`WorldMapMode`) and the NanoCom's minimap (`cnGUINanocom`), as the client stores them.

```
map/
  manifest.json
  payzone_001.png … payzone_004.png      the world map, one image per zoom step
  freezone_001.png, freezone_002.png     the Future's and the tutorial square's map
  darkland_001.png, darkland_002.png     the Dark Lands' map
  all_minimap_01.png … all_minimap_16.png  the minimap, a 4 × 4 grid of sheets
  all_minimap.png                        the whole minimap in one image
```

**Every image covers the whole map**, `[0, 8192)` metres both ways (the 16 × 16 tiles of `areas/`), north up, at its own resolution: 1024 or 2048 pixels square, the minimap sheets 512. The zones' images show their zone, with filler around it. Rectangles in the manifest are `[x, y, width, height]` in metres, x east and y north, as in `areas.json`.

Manifest fields:

| Field | |
|---|---|
| `size` | `8192`: the side of the square every image covers, in metres |
| `world` | the world map's zoom steps, widest first: `[{"file", "span"}]`. `span` is how much of the map's width the client shows at that step (1, 0.5, 0.25, 0.1159668). The widest step shows the whole map |
| `zones` | `{"future", "darklands", "tutorial"}`, each `{"rect", "levels"}`: a player inside `rect` gets that zone's map instead of the world map, kept within `rect`. `levels` are its zoom steps as in `world`; the Future and the Dark Lands open at step 3 of 4, the tutorial at step 4 |
| `minimap` | `{"all": "all_minimap.png", "sheets": [{"file", "rect"}]}`: sheet `NN` covers a 2048 m square, numbered from the north-west corner across and then south (sheet 01 is `[0, 6144, 2048, 2048]`, sheet 16 `[6144, 0, 2048, 2048]`) |

The three builds have the same images. Missing ones are left out of the manifest.

## avatar/

What a player character is made of, as the client builds it (`cnAvatarStatus`, `ActorSkinCombiner`).

```
avatar/
  manifest.json
  actor/m/default.glb         the boy actor (actor/m.kfm), no animation clips
  actor/m/clips/<clip>.glb    each of its animation clips
  actor/w/...                 the girl (actor/w.kfm)
  wear/<model>/<variant>.glb  everything players wear (wear/<model>.nif)
  wear/<model>/clips/<clip>.glb
  textures.json               texture name → shared/ file
  palettes.json               skin and hair colours (male.bsd)
  hnpc.json                   human NPC looks (all_hnpc.asset)
  tables.json                 XDT tables
  emote/<name>.png            the chat menu's emote icons
  shared/
```

**Prefab folders.** Each prefab (an actor or a worn model) has a folder of its own:

- `<variant>.glb`: the model, once per set of textures the XDT puts on it. The variant is named by the set's first texture (`m_face_001_a`), or by both joined with `+` when that isn't enough to tell them apart. A prefab the XDT names no textures for has just `default.glb`, with its own.
- `clips/<clip>.glb`: each animation clip on its own, with the same nodes in the same order as the model and no meshes, so it plays on any variant (match by node index). A track that never moves has one keyframe.

The manifest lists them: `actors: {"m": prefab, "w": prefab}` and `wear: {model: prefab}`, where a prefab is, for example

```json
{"source": "CharacterSelection.resourceFile",
 "variants": {"default": {"file": "actor/m/default.glb"}},
 "clips": {"run": "actor/m/clips/run.glb", "stand1": "actor/m/clips/stand1.glb"}}
```

or, for a worn item the XDT gives textures,

```json
{"source": "CharacterSelection.resourceFile",
 "variants": {"m_head_001_a": {"file": "wear/m_head_001_type02/m_head_001_a.glb", "textures": ["m_head_001_a", null]}},
 "left_out": 53,
 "warnings": ["..."]}
```

`textures` is the XDT's set (first and second texture). `left_out` counts the plain meshes left out of a worn item. `clips` is missing when there are none.

**Worn and attached.** The client skins clothes, capes, faces and hair into the character (the XDT says which). Those are exported with their skinned meshes only, as the client combines them: some hair carries 3ds Max helper boxes the game never draws. Hats, glasses, weapons and back items are attached whole and are exported whole.

**Binding to the actor.** Bone names aren't unique, so worn items bind through tables (`--actor-bones` in UnityPackFF):

- the actor's root node has `extras.actor_bones`: the `ActorSkinCombiner.actorBones` list as node indices;
- each worn item's skin has `extras.actor_bones = {"m": [...], "f": [...]}`, one entry per joint: the index into the boy's or the girl's list (−1 for none).

**Height and build.** The `shape` and `height` animation clips animate `_FatFactor` on the materials. glTF can't animate material values, so these curves are in the animation's `extras.float_curves` (`{"<path>:<attribute>": {"input", "output", "node"}}`, accessors).

**`textures.json`**: `{name: "shared/<file>.png"}` for every texture the XDT names for something players wear (including `m_skin`, `f_skin`, every eye colour of every face) and every texture a human NPC names. A character builder swaps them in by name. Manifest `missing_textures`: names the XDT uses that the client doesn't have.

**`palettes.json`**: `{"skin": [[r, g, b, a] × 20], "hair": [...]}`, from `male.bsd`. The client picks `skin[SkinColor − 1]` and `hair[HairColor − 1]`.

**`hnpc.json`**: the rows of `all_hnpc.asset` (`TableElement`) as they are: `iType`, `strHairMesh`, `strHairTexture`, …, `iHeight`, `iShape`, `iSkinColor`, `iHairColor`. Mesh and texture names are the client's (`f_head_014_type01.nif`, `f_head_014_a.dds`). NPC rows refer to them by `m_iHNpcNum`.

**`tables.json`**: `{table: {list: rows}}` from the client's XDT: the item tables' `m_pItemData`, `m_pItemMeshData`, `m_pItemStringData` and `m_pItemIconData` (shirts, pants, shoes, hats, glasses, back items, weapons, vehicles, faces, hair), `m_pNpcTable` (`m_pNpcData`, `m_pNpcMeshData`, `m_pNpcStringData`, `m_pNpcIconData`), `m_pAvatarTable`, `m_pAnimationTable.m_pAvatarData` and `m_pEmoteTable`. These are the client's own tables. A row's name is its table's string list at the row's name index (`m_iItemName`, `m_iNpcName`): `m_strName`, with `m_strComment` the description. Its icon is its table's icon list at the row's icon index (`m_iIcon`; NPCs and nanos `m_iIcon1`), `{m_iIconNumber, m_iIconType}`, which names a file in `icons/` as the client does: `<prefix>_<number, two digits or more>.png`, the prefix by type: 0 `wpnicon`, 1 `nanoicon`, 2 `skillicon`, 3 `cosicon`, 4 `npcicon`, 5 `nanoready`, 6 `questitemicon`, 7 `generalitemicon`, 8 `mobicon`, 9 `fusionicon`, 10 `hnpcicon`, 11 `transport`, 12 `vehicle`.

**`emote/`**: the chat menu's emote icons (`angryicon.png`, …).

## models/

```
models/
  manifest.json
  mob/<model>/<variant>.glb     NPCs, mobs, shinies, the bus (mob/<model>.kfm)
  mob/<model>/clips/<clip>.glb
  nano/<model>/...              nanos (nano/<model>.kfm)
  textures.json
  tables.json
  shared/
```

Prefab folders and the manifest's prefab entries are as in `avatar/`; the manifest has `mob: {model: prefab}` and `nano: {model: prefab}`. A prefab held by several archives is taken from the shared ones first (World_shared, Freearea, TrainingGrounds, Tutorial, the nano archives) and then the per-tile DongResources. The XDT texture rule for these is the client's: on each renderer's first material only, a material named `…sub…` takes the second texture and one named `…main…` the first. NPC types 100 and up and human NPCs keep the prefab's own.

The root node is where the client places the NPC. Every animation clip is exported, including `nif-default`, the bind pose the client never plays.

**`textures.json`**: as in `avatar/`, for the textures the XDT names for mobs, NPCs, shinies, the bus and nanos.

**`tables.json`**: `m_pNpcTable` (`m_pNpcData`, `m_pNpcMeshData`, `m_pNpcStringData`, `m_pNpcIconData`), `m_pNanoTable` (`m_pNanoData`, `m_pNanoMeshData`, `m_pNanoStringData`, `m_pNanoIconData`), `m_pShinyTable` (data, mesh and string rows), `m_pTransportationTable` (data and mesh rows), and `m_pAnimationTable` (`m_pNpcData`, `m_pNanoData`). An NPC row's `m_iMesh` indexes its table's mesh rows, whose `m_pstrMMeshModelString` is the prefab's `<model>`, and its `m_iNpcName` its string rows, whose `m_strName` is its name (nanos: `m_iNanoName`; shinies: `m_iShinyName`), and its `m_iIcon1` its icon rows (the icon file as in `avatar/`). `m_iRadius` and `m_iHeight` (centimetres) are the NPC's hitbox cylinder, `m_fScale` the model's scale. Variants of a creature (the same model in other sizes, a boss among them) are rows of their own: their names, levels and scales differ, and `m_iDifficulty` is 2 for the big ones.

## media/

```
media/
  manifest.json
  vo/<name>.ogg          NPC voice lines (vo/)
  story/<name>.ogg       Dexter's lab and the tutorial (cc sound/, tut sound/)
  hints/<name>.ogg       Computress's first-use hints (fu sound/)
  nano/<name>.ogg        nano voices (sound/<…>_nan…)
  ep/big_NN.png          Infected Zone banners by EP id
  ep/small_NN.png
  csbg/<zone>_<n>.png    character select backdrop panels
  help/<name>.jpg        the guide's pictures
```

Manifest fields:

| Field | |
|---|---|
| `voices` | `{speaker: [line, ...]}`: `vo/<speaker>_<line>.ogg` |
| `story`, `hints` | file names in `story/` and `hints/` |
| `nanos` | `{prefab: {animation clip: [file, ...]}}`: the voice files the `sound` events of each of a nano's animation clips play (`AnimationEventHandler`), with `(RAND:a-b)` ranges expanded, files in `nano/` |
| `dismiss` | `{name: [file, ...]}`: the dismiss lines `NanoContainer` plays by the nano's display name (`dee_dee`, `prof._utonium`), files in `nano/` |
| `nano_voices` | every voice file in `nano/`, including takes no event plays |
| `ep` | `{"big": [id, ...], "small": [...]}` |
| `backdrops` | `{zone: [panel, ...]}`: zones `future`, `suburbs`, `downtown`, `wilds`, `darklands`; panels 1–10, 542 × 477 each, shown side by side in order (`CnGuiCharSelection`) |
| `help` | names in `help/` |

The guide's pictures are JPEGs in the client's container (`help/*.jpg`) and are written as JPEG at quality 90. Everything else is as stored.

## world/

```
world/
  manifest.json
  tile/<XX_YY>.glb               one per map tile scene (Map_XX_YY)
  effect/<name>.glb              the effect prefabs the tiles' scripts place
  shared/
  attr/<XX_YY>.bin               the tile's MapAttributeTable
  sky/<set>/skybox_<side>tex.png
  bgm/<file>.ogg                 music and ambient tracks
```

**Tiles.** Every `Map_XX_YY` scene, exported whole by UnityPackFF (`GLTFWriter.add_scene`), **at its world position**: the scene root keeps its translation (Map_04_02's is `[-2048, 0, 1024]` in glTF), so tiles placed side by side line up without moving them. That includes the instance tiles (XX or YY ≥ 16). Each tile has:

- every active GameObject: props with their materials (raw Unity material in `extras`), water planes, skinned and animated props, with each Animation component's clips and how it plays them (`extras.animation` on its node);
- the terrain: a mesh with the heightmap's shifts applied, a base colour texture blended from the splats, and in the material's `extras.terrain`: the splat textures with their tiling, the control maps, the lightmap, and the details (grass prototypes, wind, a density texture per prototype);
- lights (`KHR_lights_punctual`);
- each node's scripts and their fields (`extras.scripts`, UnityPackFF's `scripts`: `[{"script": class name, "enabled", "fields"}]`): the effects the client places at runtime (`EffectEmitterController`), the Infected Zones' moving platforms, rings, jump pads and slides (`Ep*Trigger`, `EPElementController`) and their waypoints (`Waypoint`). Fields are as stored: vectors in Unity's coordinates (not mirrored), colours as `[r, g, b, a]`; a pointer to another node is `{"node": n}` (plus `"component"` when it names a script on it), anything else `{"object", "type", "path"}`. A script of an unknown class with no fields of its own (Unity's built-in ones) is left out;
- in the scene's `extras`: `render_settings` (fog, fog colour and density, ambient light) and `colors` (FusionFall's DongColorSetup: fog depth, fog, sky and light colours).

Manifest `tiles`: `{"XX_YY": {"terrain": bool, "attributes": {"size": 129, "poison": cells, "heal": cells}, "warnings": n}}`. Manifest `skipped`: tiles that couldn't be read, with why (104 and 728 have 32 tile scenes without type trees, `Map_16_12` to `Map_23_15`, which nothing can read).

Manifest `partial`: `true` when ff-unpack was asked for only some tiles (`--tiles`), `false` for a whole world. A reader that draws missing tiles as sea must not do so for a partial pack. ff-unpack never replaces a whole world pack with a partial one.

**`effect/<name>.glb`**: each prefab an `EffectEmitterController` in the tiles names as its `nifObject` (the Infected Zones' barriers are `EPbarrier1`), exported once, with its animation clips (they loop) and scripts; the emitter's node places it. `<name>` is the prefab's name in lower case, and an emitter's `nifObject.object` gives it. Manifest `effects`: `{"<name>": {"file": "effect/<name>.glb", "prefab": its name, "path": its container path or null}}`. `path` is null when no container lists the prefab (it sits in a tile's own data). When tiles hold copies of a prefab that differ, the first tile's (by name) is kept and the entry gets `"copies": n`: in 728 every tile has its own copy, compressed on its own, whose normals and texture coordinates differ slightly. The effects' particle systems aren't exported.

**`attr/<XX_YY>.bin`**: the tile's `MapAttributeTable`, 129 × 129 bytes, one per heightmap vertex (4 m apart), stored x-major: byte `x + z × 129`, with x east and z north from the tile's south-west corner. Flags: 8 = poison (standing there hurts), 16 = heal, 1 and 4 gate some items, values from 64 up mark roads and pavements. Poison overlays are drawn from this by whoever shows them.

**`sky/<set>/`**: the two skyboxes' six faces (`front`, `back`, `left`, `right`, `up`, `down`), RenderFX/Skybox: set `normal` (`Skybox.mat`) and set `fusion` (`Skybox_FreeZone.mat`). Manifest `sky`: `{"sets": ["fusion", "normal"], "fusion_rects": [[x, y, width, height], ...]}`: the client shows the fusion sky inside these map rectangles (metres, as in `areas.json`: the Future and the tutorial square), the normal one elsewhere (`cnPlayerCamera`).

**`light`** (manifest): main.unity3d's directional light, the sun every tile is lit by: `{"direction": [x, y, z], "color": [r, g, b], "intensity": n}`. `direction` points towards the light, in glTF space.

**Music** (manifest): `music` and `ambient`, the zones of `MusicDataStorage`: `[{"index", "name", "file", "delay", "instance", "points": [[x, y], ...]}]`. `points` is a polygon in metres on the map. `file` is in `bgm/` (`null` plays silence). The client plays the track of the first zone that contains the player and whose `instance` flag matches whether the player is in an instance. `tracks`: the files in `bgm/`.

## glTF

Everything in `.glb` files is UnityPackFF's glTF export; its README describes it in full. In short:

- Each material keeps the Unity material it came from in `extras`: the shader name, `colors`, `floats` and `textures` (with glTF texture indices). Render state (alpha mode, double-sided) comes from FusionFall's shader names. A renderer picks its shader by `extras.shader`.
- Skins use the meshes' stored bind poses. Clips are sampled at each clip's rate and interpolated linearly. Material curves are in the animation's `extras.float_curves`; a clip that animates only materials is in the document's `extras.material_clips`.
- A node with an Animation component has `extras.animation`: the clip list in order, the default clip, the wrap mode, and whether it plays automatically.

## Versions

`format_version` goes up when something a reader may rely on changes or goes away: a file or folder is moved or renamed, a field is removed or renamed, or a value changes its meaning, units or coordinates. It stays the same for additions: a new sub-pack, new files, new fields in a manifest or a JSON file. Readers ignore what they don't know.

Every change is listed below, additions too, with the ff-unpack version that first writes it (the manifests' `ff_unpack`). A reader that needs an addition checks that version.

| `format_version` | ff-unpack | Changes |
|---|---|---|
| 1 | 0.1.0 | first version: `areas/`, `icons/`, `avatar/`, `models/`, `media/`, `world/` |
| 1 | 0.2.0 | new sub-pack `map/`: the world map and the minimap |
| 1 | 0.3.0 | `avatar/` and `models/` `tables.json`: the XDT tables' string lists (names) and icon lists |
