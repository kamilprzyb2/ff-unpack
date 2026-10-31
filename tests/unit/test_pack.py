import json
import os

import pytest

from ff_unpack.builds import Build
from ff_unpack.pack import Staging, fingerprint, safe


def test_safe_names():
    assert safe("Fourarms_NanSummon01") == "fourarms_nansummon01"
    assert safe("buddy_window - tight") == "buddy_window_-_tight"
    assert safe("a/b\\c") == "a_b_c"
    assert safe("m_head_001_a@x") == "m_head_001_a@x"


def test_fingerprint_ignores_order():
    a = fingerprint({"A.resourceFile": "1" * 64, "B.resourceFile": "2" * 64})
    b = fingerprint({"B.resourceFile": "2" * 64, "A.resourceFile": "1" * 64})
    assert a == b and len(a) == 64
    assert a != fingerprint({"A.resourceFile": "1" * 64, "B.resourceFile": "3" * 64})


def test_staging_swaps_in_whole(tmp_path):
    build = Build(104)
    with Staging(tmp_path, build, "base") as s:
        s.sources = {"TableData.resourceFile": "ab" * 32}
        s.manifest["areas"] = 1
        with open(s.path("areas.json"), "w") as f:
            f.write("[]")
        # nothing is in place until the block ends
        assert not os.path.exists(tmp_path / "beta-20100104" / "base")
    final = tmp_path / "beta-20100104" / "base"
    m = json.loads((final / "manifest.json").read_text())
    assert m["format"] == "ff-unpack/base"
    assert m["format_version"] == 1
    assert m["build"] == {"protocol": 104, "name": "beta-20100104", "uuid": build.manifest["uuid"]}
    assert m["sources"] == {"TableData.resourceFile": "ab" * 32}
    assert m["fingerprint"] == fingerprint(m["sources"])
    assert m["areas"] == 1
    assert (final / "areas.json").read_text() == "[]"
    # only the pack is left: no work directories
    assert os.listdir(tmp_path / "beta-20100104") == ["base"]


def test_staging_keeps_the_old_pack_on_failure(tmp_path):
    build = Build(728)
    with Staging(tmp_path, build, "media") as s:
        with open(s.path("old.txt"), "w") as f:
            f.write("old")
    with pytest.raises(RuntimeError):
        with Staging(tmp_path, build, "media") as s:
            with open(s.path("new.txt"), "w") as f:
                f.write("new")
            raise RuntimeError("stage failed")
    final = tmp_path / "beta-20100728" / "media"
    assert sorted(os.listdir(final)) == ["manifest.json", "old.txt"]
    assert os.listdir(tmp_path / "beta-20100728") == ["media"]


def test_builds():
    for proto, name in ((104, "beta-20100104"), (728, "beta-20100728"), (1013, "beta-20111013")):
        b = Build(proto)
        archives = b.archives()
        assert b.name == name
        assert "main.unity3d" in archives and "TableData.resourceFile" in archives
        url, info, inner = archives["TableData.resourceFile"]
        assert url.endswith("/" + name + "/TableData.resourceFile")
        assert len(info["hash"]) == 64 and info["size"] > 0
        assert inner and all(len(v["hash"]) == 64 for v in inner.values())
        # files refer to each other in lowercase
        where = b.archive_of_file()
        assert all(k == k.lower() for k in where)
        assert set(where.values()) <= set(archives)
    with pytest.raises(KeyError):
        Build(105)
