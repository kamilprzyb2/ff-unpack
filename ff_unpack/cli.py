"""ff-unpack: unpack the FusionFall client into packs.

    ff-unpack OUT --build 104 base avatar models media world
    ff-unpack OUT --build 1013 areas
    ff-unpack --list-stages

Downloads the client's archives for the build from the CDN its launcher
manifest names (each checked against the manifest's SHA-256, and kept in
the cache), and writes one sub-pack per stage to OUT/<build>/<sub-pack>/
(PACK_FORMAT.md). Each sub-pack is written beside its final place and
swapped in whole.

Stages:
  areas   base/: the client's named areas only (TableData, ~4 MB download)
  base    base/: the named areas and the icons
  avatar  avatar/: the boy and girl actors with every clip, everything
          players wear, colour palettes, human NPC looks, emote icons
  models  models/: every mob, NPC and nano prefab with every clip
  media   media/: voice lines, story and hint clips, nano voices, banners,
          character select backdrops, guide pictures
  world   world/: every map tile, attribute grids, skyboxes, music zones
          and tracks
"""

import argparse
import logging
import os
import sys
import time

from . import __version__
from .builds import BUILDS, Build
from .client import Client, FetchError, default_cache
from .pack import Staging
from .plan import seeds
from .stages import STAGES, options as stage_options
from .stages.common import needed


def run_stage(client, out, stage, options):
    start = time.monotonic()
    client.log(f"{client.build.name}: {stage.name}")
    if hasattr(stage, "check"):
        stage.check(os.path.join(out, client.build.name, stage.subpack), options)
    archives = seeds(client.build, stage, options)
    used = needed(client, archives)
    with Staging(out, client.build, stage.subpack) as staging:
        staging.sources = {a: client.sha256(a) for a in used}
        staging.manifest["stage"] = stage.name
        summary = stage.run(client, staging, archives, options)
    client.log(f"  {summary} in {staging.final} ({time.monotonic() - start:.0f} s)")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ff-unpack", description="\n\n".join(__doc__.split("\n\n")[1:3]),
        epilog="\n\n".join(__doc__.split("\n\n")[3:]),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("out", nargs="?", help="where the packs go (OUT/<build>/<sub-pack>/)")
    p.add_argument("stages", nargs="*", help="stages to run: " + ", ".join(STAGES))
    p.add_argument("--build", type=int, choices=sorted(BUILDS), default=104,
                   help="the server protocol whose client to unpack (default: 104)")
    p.add_argument("--cache", default=None, help=f"where downloaded archives are kept (default: {default_cache()})")
    p.add_argument("--jobs", type=int, default=2, help="processes for the stages that use several (default: 2)")
    p.add_argument("--tiles", default=None, metavar="XX_YY,...",
                   help="world stage: only these tiles (to try a change on one area; the pack lists only them)")
    p.add_argument("--list-stages", action="store_true", help="list the stages and exit")
    p.add_argument("--version", action="version", version=f"ff-unpack {__version__}")
    args = p.parse_intermixed_args(argv)

    if args.list_stages:
        for name, stage in STAGES.items():
            print(f"{name}\t{stage.subpack}/")
        return 0
    if not args.out or not args.stages:
        p.error("give the output directory and at least one stage")
    unknown = [s for s in args.stages if s not in STAGES]
    if unknown:
        p.error(f"unknown stage {unknown[0]} (choose from {', '.join(STAGES)})")

    # Files without type trees log a warning per class they lack; the
    # stages report what they skip themselves.
    logging.disable(logging.WARNING)
    options = stage_options(args.jobs, [t.strip() for t in (args.tiles or "").split(",") if t.strip()])
    client = Client(Build(args.build), args.cache)
    try:
        for name in dict.fromkeys(args.stages):
            run_stage(client, args.out, STAGES[name], options)
    except (FetchError, RuntimeError) as e:
        print(f"ff-unpack: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
