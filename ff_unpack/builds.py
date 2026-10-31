"""The client builds ff-unpack knows, each pinned by its launcher manifest.

A launcher manifest (as OpenFusionLauncher ships them in
resources/defaults/versions/, and ofapi serves them at /versions/<uuid>.json)
lists every archive of a build with its URL and SHA-256, and the SHA-256 of
every file inside it (main.unity3d excepted). The three in manifests/ are
copied unchanged from OpenFusionLauncher.
"""

import json
from importlib import resources

# server protocol -> client build
BUILDS = {104: "beta-20100104", 728: "beta-20100728", 1013: "beta-20111013"}
MAIN_FILE = "main.unity3d"


class Build:
    def __init__(self, protocol):
        if protocol not in BUILDS:
            raise KeyError(f"unknown protocol {protocol} (choose from {', '.join(map(str, BUILDS))})")
        self.protocol = protocol
        self.name = BUILDS[protocol]
        with resources.files("ff_unpack").joinpath("manifests", f"{self.name}.json").open() as f:
            self.manifest = json.load(f)

    def __repr__(self):
        return f"<Build {self.protocol} {self.name}>"

    def as_json(self):
        return {"protocol": self.protocol, "name": self.name, "uuid": self.manifest["uuid"]}

    def archives(self):
        """{archive: (url, {"hash", "size"}, {file inside: {"hash", "size"}} or None)}"""
        base = self.manifest["asset_url"].rstrip("/")
        out = {
            name: (f"{base}/{name}", info["compressed_info"], info.get("uncompressed_info"))
            for name, info in self.manifest["bundles"].items()
        }
        # The manifest has no hashes for the files inside the main archive.
        out[MAIN_FILE] = (self.manifest["main_file_url"], self.manifest["main_file_info"], None)
        return out

    def archive_of_file(self):
        """{file inside an archive, lowercased: archive}. Files refer to each
        other by these names (customassetbundle-<id>), in lowercase."""
        out = {}
        for archive, (_, _, inner) in self.archives().items():
            for name in inner or ():
                out[name.lower()] = archive
        return out
