"""The `media` sub-pack: voices and UI art.

    vo/<name>.ogg       NPC voice lines (vo/<speaker>_<kind>NN.wav)
    story/<name>.ogg    Dexter's lab and the tutorial (cc sound/, tut sound/)
    hints/<name>.ogg    Computress's first-use hints (fu sound/)
    nano/<name>.ogg     nano voices: what the nano's animation clips' events
                        play, and the dismiss lines (sound/<name>_NanDismiss0N)
    ep/big_NN.png       Infected Zone banners by EP id, and their small
    ep/small_NN.png     versions
    csbg/<zone>_N.png   the ten panels of each zone's character select
                        backdrop, as the client stores them
    help/<name>.jpg     the in-game guide's pictures

Every .wav and .mp3 in the client is an Ogg Vorbis file inside (AudioClip
format 5), copied as it is."""

import io
import re

from unitypack.gltf import components

from ..pack import safe
from .common import AUDIO_CLIP, GAME_OBJECT, TEXTURE_2D, TRANSFORM, basename, find, texture_png, write_bytes
from .prefabs import gameobject

SUBPACK = "media"
ANIMATION = 111
FOLDERS = {"vo/": "vo", "cc sound/": "story", "tut sound/": "story", "fu sound/": "hints"}
NANO_SOUND = re.compile(r"^sound/[^/]*_nan[^/]*\.(wav|mp3|ogg)$")
DISMISS = re.compile(r"^(.+)_nandismiss0[1-3]$")
NANO_PREFAB = re.compile(r"^nano/(.+)\.kfm$")
# "Fourarms_NanSummon0(RAND:1-3).wav" (AnimationEventHandler.PlaySound)
RAND = re.compile(r"\(RAND:(\d+)-(\d+)\)")
EP = re.compile(r"(^|/)ep_(big|small)_(\d+)\.png$")
# CnGuiCharSelection: the zone a character is in picks the backdrop
ZONES = {"csfuturebg": "future", "cssuburbsbg": "suburbs", "csdowntownbg": "downtown", "cswildsbg": "wilds",
         "csdarklandsbg": "darklands"}
CSBG = re.compile(r"(^|/)(" + "|".join(ZONES) + r")_(\d+)\.png$")
HELP = re.compile(r"^help/(.+)\.(jpg|png)$")


def audio_folder(path):
    for prefix, folder in FOLDERS.items():
        if path.startswith(prefix):
            return folder
    return "nano" if NANO_SOUND.match(path) else None


def seed(e):
    if e.class_id == AUDIO_CLIP:
        return audio_folder(e.path) is not None
    if e.class_id == TEXTURE_2D:
        return bool(EP.search(e.path) or CSBG.search(e.path) or HELP.match(e.path))
    return e.class_id in (GAME_OBJECT, TRANSFORM) and bool(NANO_PREFAB.match(e.path))


def sounds(event):
    """The files a clip's sound event plays: RAND ranges expanded."""
    m = RAND.search(event)
    if not m:
        return [event.rsplit(".", 1)[0]]
    lo, hi = int(m.group(1)), int(m.group(2))
    return [(event[:m.start()] + str(i) + event[m.end():]).rsplit(".", 1)[0] for i in range(lo, min(hi, lo + 20) + 1)]


def nano_events(client, entry):
    """{clip: [voice file names]} of a nano prefab: the `sound` events of
    its animation clips that play its voice (the `_Nan` ones)."""
    go = gameobject(client, entry)
    out = {}
    if go is None:
        return out
    for class_id, ptr in components(go):
        if class_id != ANIMATION:
            continue
        for clip_ptr in ptr.resolve()._obj["m_Animations"]:
            clip = clip_ptr.resolve() if clip_ptr else None
            if clip is None:
                continue
            c = clip._obj
            lines = [
                safe(f)
                for ev in c.get("m_Events", [])
                if ev.get("functionName") == "sound" and "_nan" in (ev.get("data") or "").lower()
                for f in sounds(ev["data"])
            ]
            if lines:
                out[c["m_Name"].lower()] = lines
    return out


def jpeg(png_bytes):
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(png_bytes)).convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


class Media:
    name = "media"
    subpack = SUBPACK
    fixed = []
    seed = staticmethod(seed)

    @staticmethod
    def run(client, staging, archives, options):
        audio = {"vo": set(), "story": set(), "hints": set(), "nano": set()}
        for e in find(client, archives, lambda e: e.class_id == AUDIO_CLIP and audio_folder(e.path)):
            folder, name = audio_folder(e.path), safe(basename(e.path))
            data = bytes(client.object(e).read()._obj["audio data"] or b"")
            if data[:4] != b"OggS":
                client.log(f"  warning: {e.path} is not Ogg Vorbis inside; skipped")
                continue
            write_bytes(staging.path(folder, f"{name}.ogg"), data)
            audio[folder].add(name)

        voices = {}
        for name in sorted(audio["vo"]):
            speaker, _, line = name.rpartition("_")
            voices.setdefault(speaker, []).append(line)

        # Nano voices: by prefab and clip, as the events name them (takes
        # past a RAND range the client never plays aren't listed), and the
        # dismiss lines by the nano's display name, as NanoContainer plays
        # them.
        events = {}
        for e in find(client, archives, lambda e: e.class_id in (GAME_OBJECT, TRANSFORM) and NANO_PREFAB.match(e.path)):
            clips = {c: [f for f in files if f in audio["nano"]] for c, files in nano_events(client, e).items()}
            clips = {c: f for c, f in sorted(clips.items()) if f}
            if clips:
                events[NANO_PREFAB.match(e.path).group(1)] = clips
        dismiss = {}
        for name in sorted(audio["nano"]):
            m = DISMISS.match(name)
            if m:
                dismiss.setdefault(m.group(1), []).append(name)

        ep, backdrops, helps = {"big": [], "small": []}, {}, []
        for e in find(client, archives, lambda e: e.class_id == TEXTURE_2D):
            m = EP.search(e.path)
            if m:
                size, number = m.group(2), int(m.group(3))
                write_bytes(staging.path("ep", f"{size}_{number:02d}.png"), texture_png(client.object(e).read()))
                ep[size].append(number)
                continue
            m = CSBG.search(e.path)
            if m:
                zone, panel = ZONES[m.group(2)], int(m.group(3))
                write_bytes(staging.path("csbg", f"{zone}_{panel}.png"), texture_png(client.object(e).read()))
                backdrops.setdefault(zone, []).append(panel)
                continue
            m = HELP.match(e.path)
            if m:
                name = safe(m.group(1))
                write_bytes(staging.path("help", f"{name}.jpg"), jpeg(texture_png(client.object(e).read())))
                helps.append(name)

        staging.manifest.update(
            voices=voices,
            story=sorted(audio["story"]),
            hints=sorted(audio["hints"]),
            nanos=events,
            dismiss=dismiss,
            nano_clips=sorted(audio["nano"]),
            ep={k: sorted(v) for k, v in ep.items()},
            backdrops={z: sorted(p) for z, p in sorted(backdrops.items())},
            help=sorted(helps),
        )
        lines = sum(len(v) for v in voices.values())
        return (f"{lines} voice lines of {len(voices)} speakers, {len(audio['nano'])} nano voice files "
                f"({len(events)} nanos with events), {len(audio['story'])} story and "
                f"{len(audio['hints'])} hint recordings, "
                f"{len(ep['big'])} EP banners, {len(backdrops)} backdrops, {len(helps)} help pictures")
