#!/usr/bin/env python3
"""Regenerates src/ff_unpack/archives.json: for each build and stage, the
archives whose containers hold something the stage exports.

Needs every archive of each build in the cache (it downloads what's
missing, about 0.5 GB per build):

    python3 tools/plan_archives.py [--cache DIR] [--build 104 ...]
"""

import argparse
import json
import logging
import os
import sys

import ff_unpack
from ff_unpack.builds import BUILDS, Build
from ff_unpack.client import Client
from ff_unpack.stages import STAGES

# the checkout's, with ff-unpack installed from it (pip install -e .)
OUT = os.path.join(os.path.dirname(os.path.abspath(ff_unpack.__file__)), "archives.json")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--cache", help="the archive cache (default: ff-unpack's)")
    p.add_argument("--build", type=int, action="append", help="only these builds (default: all)")
    p.add_argument("--jobs", type=int, default=4, help="downloads at once")
    args = p.parse_args()
    logging.disable(logging.WARNING)

    plan = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            plan = json.load(f)
    for proto in args.build or BUILDS:
        client = Client(Build(proto), args.cache)
        archives = sorted(client.build.archives())
        client.fetch(archives, args.jobs)
        found = {name: set() for name in STAGES}
        for a in archives:
            for e in client.entries(a):
                for name, stage in STAGES.items():
                    if stage.seed(e):
                        found[name].add(a)
        plan[client.build.name] = {name: sorted(found[name]) for name in STAGES if found[name]}
        print(client.build.name, {n: len(v) for n, v in found.items()}, file=sys.stderr)
    with open(OUT, "w") as f:
        json.dump(dict(sorted(plan.items())), f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
