"""The client's archives: downloaded, checked and unpacked into a cache, and
opened with UnityPackFF.

Cache layout (the same as UnityPackFF's test cache, so one can serve both):

    <cache>/<build>/<archive>                     as downloaded
    <cache>/<build>/unpacked/<archive>/<file>     the files inside it

Every download is checked against the launcher manifest's SHA-256 before it
is kept, and so is every file inside it before it is written.
"""

import hashlib
import logging
import os
import struct
import sys
import urllib.request
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

import unitypack
from unitypack.environment import UnityEnvironment

from . import __version__
from .builds import Build

USER_AGENT = f"ff-unpack/{__version__}"
ASSET_BUNDLE = 142
# a marker in an unpacked archive's folder: the archive's SHA-256
UNPACKED_MARK = ".ff-unpack"

# One container entry of an asset file: the load path the client asks for
# (lowercased), and the object it names (the file holding it, its path ID,
# its class ID; class None when the object is in a file not unpacked).
Entry = namedtuple("Entry", "archive file path target path_id class_id")


class FetchError(Exception):
    pass


def default_cache():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "ff-unpack")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_serialized(path):
    """Whether a file looks like a serialized asset file (not a DLL or a
    resource stream that sits beside them in an archive)."""
    with open(path, "rb") as f:
        head = f.read(16)
    if len(head) < 16:
        return False
    metadata_size, file_size, fmt, _ = struct.unpack(">4I", head)
    return 5 <= fmt <= 9 and file_size == os.path.getsize(path) and metadata_size < file_size


def _safe_name(name):
    if not name or name in (".", "..") or any(c in name for c in "/\\\0"):
        raise FetchError(f"refusing the file name {name!r}")
    return name


class Client:
    """One build's archives in a cache. Open files are kept for the life of
    the object, so make one per process."""

    def __init__(self, build, cache=None, quiet=False):
        self.build = build if isinstance(build, Build) else Build(build)
        self.cache = cache or default_cache()
        self.root = os.path.join(self.cache, self.build.name)
        self.unpacked = os.path.join(self.root, "unpacked")
        self.quiet = quiet
        self._archives = self.build.archives()
        self._env = None
        self._files = None
        self._entries = {}

    def log(self, msg):
        if not self.quiet:
            print(msg, file=sys.stderr, flush=True)

    # --- fetching ----------------------------------------------------------

    def has(self, archive):
        return archive in self._archives

    def sha256(self, archive):
        return self._archives[archive][1]["hash"]

    def _download(self, archive):
        url, want, _ = self._archives[archive]
        dest = os.path.join(self.root, _safe_name(archive))
        if os.path.exists(dest) and os.path.getsize(dest) == want["size"] and sha256_file(dest) == want["hash"]:
            return False
        os.makedirs(self.root, exist_ok=True)
        tmp = f"{dest}.{os.getpid()}.part"
        h = hashlib.sha256()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
                for chunk in iter(lambda: resp.read(1 << 20), b""):
                    h.update(chunk)
                    out.write(chunk)
        except OSError as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise FetchError(f"{url}: {e}") from e
        if h.hexdigest() != want["hash"]:
            os.remove(tmp)
            raise FetchError(f"{url}: SHA-256 {h.hexdigest()}, but the manifest says {want['hash']}")
        os.replace(tmp, dest)
        return True

    def _is_unpacked(self, archive):
        folder = os.path.join(self.unpacked, archive)
        _, want, inner = self._archives[archive]
        mark = os.path.join(folder, UNPACKED_MARK)
        if os.path.exists(mark):
            with open(mark) as f:
                return f.read().strip() == want["hash"]
        # Unpacked by something else (UnityPackFF's tests): trust files of
        # the right sizes; the main archive's have none to check.
        if inner is None or not os.path.isdir(folder):
            return False
        return all(
            os.path.isfile(os.path.join(folder, n)) and os.path.getsize(os.path.join(folder, n)) == info["size"]
            for n, info in inner.items()
        )

    def _unpack(self, archive):
        _, want, inner = self._archives[archive]
        with open(os.path.join(self.root, archive), "rb") as f:
            bundle = unitypack.load(f)
            files = [(_safe_name(name), data) for name, data in bundle.files]
        if inner is not None:
            got = {n: {"hash": hashlib.sha256(d).hexdigest(), "size": len(d)} for n, d in files}
            if got != inner:
                wrong = sorted(n for n in set(got) | set(inner) if got.get(n) != inner.get(n))
                raise FetchError(f"{archive}: files inside don't match the manifest: {', '.join(wrong)}")
        folder = os.path.join(self.unpacked, archive)
        os.makedirs(folder, exist_ok=True)
        for name, data in files:
            tmp = os.path.join(folder, f".{name}.{os.getpid()}.tmp")
            with open(tmp, "wb") as out:
                out.write(data)
            os.replace(tmp, os.path.join(folder, name))
        with open(os.path.join(folder, UNPACKED_MARK), "w") as f:
            f.write(want["hash"] + "\n")

    def fetch(self, archives, jobs=4):
        """Downloads and unpacks the archives that aren't in the cache yet."""
        missing = [a for a in archives if a not in self._archives]
        if missing:
            raise FetchError(f"{self.build.name} has no {', '.join(missing)}")
        todo = [a for a in archives if not self._is_unpacked(a)]
        if not todo:
            return
        size = sum(self._archives[a][1]["size"] for a in todo)
        self.log(f"  fetching {len(todo)} archives ({size / 1e6:.0f} MB to download at most)")

        def one(archive):
            self._download(archive)
            self._unpack(archive)

        with ThreadPoolExecutor(max(1, jobs)) as pool:
            list(pool.map(one, todo))
        self._files = None

    # --- reading -----------------------------------------------------------

    @property
    def env(self):
        if self._env is None:
            self._env = UnityEnvironment(base_path=self.unpacked)
        return self._env

    def files(self, archive):
        """The serialized asset files inside an unpacked archive, by name."""
        folder = os.path.join(self.unpacked, archive)
        return sorted(
            n for n in os.listdir(folder)
            if not n.startswith(".") and is_serialized(os.path.join(folder, n))
        )

    def asset(self, name):
        """An asset file, by its name (any archive), opened in the shared
        environment so pointers into other files resolve."""
        return self.env.get_asset_by_filename(name)

    def entries(self, archive):
        """Every container entry of the archive's files, in their order."""
        if archive not in self._entries:
            out = []
            # Files without type trees log a warning per class they lack.
            root = logging.getLogger()
            level = root.level
            root.setLevel(logging.ERROR)
            try:
                for name in self.files(archive):
                    asset = self.asset(name)
                    bundle = asset.objects.get(1)
                    if bundle is None or bundle.type_id != ASSET_BUNDLE:
                        continue
                    for path, info in bundle.read()["m_Container"]:
                        ptr = info["asset"]
                        if not ptr:
                            continue
                        if ptr.file_id == 0:
                            target, obj = name, asset.objects.get(ptr.path_id)
                        else:
                            target = os.path.basename(asset.asset_refs[ptr.file_id].file_path)
                            try:
                                obj = self.asset(target).objects.get(ptr.path_id)
                            except KeyError:
                                obj = None
                        class_id = obj.type_id if obj else None
                        out.append(Entry(archive, name, path.lower(), target, ptr.path_id, class_id))
            finally:
                root.setLevel(level)
            self._entries[archive] = out
        return self._entries[archive]

    def object(self, entry):
        """The object a container entry names."""
        return self.asset(entry.target).objects[entry.path_id]

    def externals(self, name):
        """The files an asset file points into, as archive names."""
        where = self.build.archive_of_file()
        asset = self.asset(name)
        asset.objects  # loads the references too
        out = set()
        for ref in asset.asset_refs[1:]:
            archive = where.get(os.path.basename(ref.file_path).lower())
            if archive:
                out.add(archive)
        return out
