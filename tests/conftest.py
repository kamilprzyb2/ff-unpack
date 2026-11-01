"""Shared pytest setup.

    pytest                                   unit tests only (offline)
    pytest -m integration --build 104        every stage but world, on real archives
    pytest -m integration --build 104 --world
    pytest -m integration --packs DIR        check packs made earlier instead
    pytest -m integration --record           rewrite tests/expected/<build>.json

Integration tests run each stage once per build into a temporary directory
(archives come from FF_UNPACK_CACHE, default ~/.cache/ff-unpack, and are
downloaded when missing) and compare what the manifests say against
tests/expected/. Expected values are counts and checks only, never client
data.
"""

import json
import os
from pathlib import Path

import pytest

from ff_unpack.builds import BUILDS, Build

EXPECTED = Path(__file__).resolve().parent / "expected"
ALL_STAGES = ["areas", "icons", "map", "avatar", "models", "media", "world"]


def pytest_addoption(parser):
    parser.addoption("--build", action="append", type=int, default=[], dest="builds",
                     help="limit integration tests to these builds (104, 728, 1013); repeatable")
    parser.addoption("--world", action="store_true", help="include the world stage (slow)")
    parser.addoption("--packs", help="check the packs in this directory instead of making them")
    parser.addoption("--record", action="store_true", help="write tests/expected/<build>.json instead of comparing")
    parser.addoption("--jobs", type=int, default=2, help="processes for the stages that use several")


def pytest_generate_tests(metafunc):
    if "build" in metafunc.fixturenames:
        protos = metafunc.config.getoption("builds") or sorted(BUILDS)
        metafunc.parametrize("build", protos, ids=str, scope="session")


class Packs:
    """Packs for one build: made on first use, once per stage."""

    def __init__(self, config, root, proto):
        self.config = config
        self.root = root
        self.build = Build(proto)
        self.made = set()

    def __call__(self, stage):
        if stage == "world" and not self.config.getoption("--world") and not self.config.getoption("--packs"):
            pytest.skip("the world stage is slow: run with --world")
        folder = self.root / self.build.name / stage
        if self.config.getoption("--packs"):
            if not (folder / "manifest.json").exists():
                pytest.skip(f"no {stage}/ in --packs for {self.build.name}")
            return folder
        if stage not in self.made:
            from ff_unpack.cli import main

            cache = os.environ.get("FF_UNPACK_CACHE")
            args = [str(self.root), stage, "--build", str(self.build.protocol),
                    "--jobs", str(self.config.getoption("--jobs"))]
            if cache:
                args += ["--cache", cache]
            assert main(args) == 0
            self.made.add(stage)
        return folder


_packs = {}


@pytest.fixture(scope="session")
def packs(request, build, tmp_path_factory):
    if build not in _packs:
        given = request.config.getoption("--packs")
        root = Path(given) if given else tmp_path_factory.mktemp("packs")
        _packs[build] = Packs(request.config, root, build)
    return _packs[build]


class Expected:
    """tests/expected/<build>.json: {stage: {key: value}}."""

    def __init__(self, config, build):
        self.record = config.getoption("--record")
        self.path = EXPECTED / f"{build.name}.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def check(self, stage, got):
        if self.record:
            self.data[stage] = got
            self.path.parent.mkdir(exist_ok=True)
            self.path.write_text(json.dumps(dict(sorted(self.data.items())), indent=1, sort_keys=True) + "\n")
            return
        if stage not in self.data:
            pytest.fail(f"nothing recorded for {stage} in {self.path.name}: run with --record")
        assert got == self.data[stage]


@pytest.fixture
def expected(request, packs):
    return Expected(request.config, packs.build)
