# ff-unpack

Unpacks the FusionFall game client into packs: plain files in a documented layout ([PACK_FORMAT.md](PACK_FORMAT.md)) that a server's website, a model viewer or a renderer can read without knowing anything about Unity.

It downloads the client's archives for one build from the CDN its launcher manifest names, checks every file against the manifest's SHA-256, and unpacks them with [UnityPackFF](https://github.com/kamilprzyb2/UnityPackFF). Models and map tiles come out as glTF, images as PNG, sounds as Ogg Vorbis, tables as JSON.

ff-unpack only extracts. It doesn't render anything or draw any images, and it never ships a pack: you make your own from the client, on your machine. The packs are FusionFall's art, sound and data: don't commit or publish them.

## Install

Python 3.10 or newer.

```sh
pip install 'ff-unpack @ git+https://github.com/kamilprzyb2/ff-unpack'
```

or, from a checkout, `pip install -e '.[test]'`. UnityPackFF comes from its fork's `master`.

## Use

```sh
ff-unpack packs --build 104 base avatar models media world
ff-unpack packs --build 1013 areas
```

This writes `packs/beta-20100104/base/`, `packs/beta-20100104/avatar/` and so on: one directory per build, one sub-pack per stage. `--build` takes the server's protocol: 104 (beta-20100104, "Original"), 728 (beta-20100728) or 1013 (beta-20111013, "Academy").

| Stage | Writes | What | Downloads (104 / 728 / 1013) |
|---|---|---|---|
| `areas` | `base/` | the client's named areas only | 1 / 1 / 1 MB |
| `base` | `base/` | the named areas and every icon | 50 / 77 / 95 MB |
| `avatar` | `avatar/` | the boy and girl actors with every clip, everything players wear, colour palettes, human NPC looks, emote icons | 89 / 93 / 128 MB |
| `models` | `models/` | every mob, NPC and nano prefab with every clip | 399 / 435 / 588 MB |
| `media` | `media/` | voice lines, story and hint clips, nano voices, Infected Zone banners, character select backdrops, the guide's pictures | 391 / 419 / 564 MB |
| `world` | `world/` | every map tile, attribute grids, skyboxes, music zones and tracks, the sun | 470 / 578 / 613 MB |

Stages share archives, so all six together download the whole build once (about 0.5 GB). A server that shows no game content still needs the areas to name where players are: run `areas` alone. It reads only TableData.

Options:

- `--cache DIR`: where downloaded archives are kept, and unpacked (default `~/.cache/ff-unpack`). Stages share it, so the second stage downloads only what the first didn't. The layout is UnityPackFF's test cache's, so `--cache ~/.cache/unitypackff-tests` reuses archives its tests downloaded.
- `--jobs N`: processes for the stages that export many models or tiles (`avatar`, `models`, `world`; default 2). Each world tile process can take over a gigabyte of memory.

Each sub-pack is written beside its final place and swapped in when it's complete, so a server reading the packs never sees half of one, and a failed run leaves the old pack in place. Each has a `manifest.json` that says what's in it, which client archives it came from (`sources`, with their hashes) and a `fingerprint` that changes exactly when those do.

`areas`, `base` and `media` take seconds. `avatar` and `models` export thousands of glTF files and `world` every map tile, which takes by far the longest; `--jobs` spreads those three over processes.

## Develop

```sh
pip install --user -e '.[test]'
pytest                                   # unit tests, offline
pytest -m integration --build 104        # real archives: every stage but world
pytest -m integration --build 104 --world
```

The integration tests download what they need into the cache (`FF_UNPACK_CACHE`, default `~/.cache/ff-unpack`), unpack into a temporary directory, and compare counts and checks against `tests/expected/<build>.json`. With `--record` they rewrite those. With `FF_UNPACK_GLTF_VALIDATOR` set to a directory with `node_modules/gltf-validator`, they also validate a sample of the glTF files.

`ff_unpack/archives.json` pins which archives hold what each stage exports, per build. Finding that out means reading every archive's container, so `tools/plan_archives.py` does it once from a cache that has every archive. Run it after changing what a stage picks (`seed()`).

### Layout of the code

- `builds.py`: the three builds, pinned by the launcher manifests in `manifests/` (copied from OpenFusionLauncher).
- `client.py`: the archive cache (download, check, unpack) and reading the files with UnityPackFF.
- `pack.py`: staging a sub-pack and writing its manifest.
- `stages/`: one module per sub-pack; `prefabs.py` exports prefabs for `avatar` and `models`.
- `gltfclip.py`: cuts the constant tracks of clip files to one keyframe.

### What goes where

UnityPackFF decodes what's in the client's files and exports it as glTF. ff-unpack applies FusionFall's rules (which prefab is worn, which textures the XDT puts on it, where the client keeps what) and lays out the packs. A decoding problem is fixed in UnityPackFF.
