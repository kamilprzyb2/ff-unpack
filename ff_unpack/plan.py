"""Which archives each stage reads, per build (archives.json).

Finding the client's models takes reading every archive's container, so the
archives holding what a stage exports are worked out once, from a cache
with every archive of the build (tools/plan_archives.py), and pinned. When
it runs, a stage downloads those, and then whatever they point into."""

import json
from importlib import resources


def load():
    with resources.files("ff_unpack").joinpath("archives.json").open() as f:
        return json.load(f)


def seeds(build, stage):
    """The archives the stage reads for the build, before what they point into."""
    plan = load().get(build.name, {})
    named = stage.archives(build) if hasattr(stage, "archives") else []
    return sorted(set(stage.fixed) | set(named) | set(plan.get(stage.name, [])))
