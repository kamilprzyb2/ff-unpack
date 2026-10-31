"""The rules the stages apply to the client's names and data."""

import math

from unitypack.xdttextures import FIRST, WORN, Swap

from ff_unpack.client import Entry
from ff_unpack.stages import STAGES
from ff_unpack.stages.avatar import ACTOR, EMOTE, WEAR, named_textures, preferred
from ff_unpack.stages.media import CSBG, DISMISS, EP, HELP, audio_folder, sounds
from ff_unpack.stages.models import preferred as models_preferred
from ff_unpack.stages.prefabs import variant_names
from ff_unpack.stages.world import TILE, toward_light


def entry(path, class_id, archive="X.resourceFile"):
    return Entry(archive, "CustomAssetBundle-x", path, "CustomAssetBundle-x", 1, class_id)


def test_stage_names():
    assert list(STAGES) == ["areas", "base", "avatar", "models", "media", "world"]
    assert STAGES["areas"].subpack == STAGES["base"].subpack == "base"


def test_variant_names():
    assert variant_names([None]) == ["default"]
    one = [Swap("nano_eddy", None, FIRST)]
    assert variant_names(one) == ["nano_eddy"]
    # the first texture tells them apart
    cars = [Swap("npc_car_red", None, FIRST), Swap("npc_car_blue", None, FIRST)]
    assert variant_names(cars) == ["npc_car_red", "npc_car_blue"]
    # it doesn't: both
    shirts = [Swap("shirt_a", "m_skin", WORN), Swap("shirt_a", "f_skin", WORN)]
    assert variant_names(shirts) == ["shirt_a+m_skin", "shirt_a+f_skin"]
    # nor do both
    same = [Swap("x", None, FIRST), Swap("x", None, WORN)]
    assert variant_names(same) == ["x", "x-2"]


def test_sound_events():
    assert sounds("Fourarms_NanSummon0(RAND:1-3).wav") == [
        "Fourarms_NanSummon01", "Fourarms_NanSummon02", "Fourarms_NanSummon03"]
    assert sounds("Eddy_NanCall01.wav") == ["Eddy_NanCall01"]


def test_audio_folders():
    assert audio_folder("vo/blossom_greet01.wav") == "vo"
    assert audio_folder("cc sound/dexter_cc01.wav") == "story"
    assert audio_folder("tut sound/computress_tut01.wav") == "story"
    assert audio_folder("fu sound/computress_firstuse01.wav") == "hints"
    assert audio_folder("sound/fourarms_nansummon01.wav") == "nano"
    assert audio_folder("sound/m_avatar_cheer01.wav") is None
    assert audio_folder("bgm/01 midtown.ogg") is None
    assert DISMISS.match("dee_dee_nandismiss02").group(1) == "dee_dee"


def test_ui_art_paths():
    # 104/728 under charactercreationassets/, 1013 under uiassets/
    assert EP.search("charactercreationassets/ep_big_07.png").group(2, 3) == ("big", "07")
    assert EP.search("uiassets/ui_ep/ep_small_12.png").group(2, 3) == ("small", "12")
    assert CSBG.search("charactercreationassets/csfuturebg_10.png").group(2, 3) == ("csfuturebg", "10")
    assert CSBG.search("uiassets/ui_csbgs/csdarklandsbg_1.png").group(2, 3) == ("csdarklandsbg", "1")
    assert HELP.match("help/buddy_window - tight.jpg").group(1) == "buddy_window - tight"
    assert EMOTE.search("tutorialassets/emotechaticon/angryicon.png").group(3) == "angryicon"
    assert EMOTE.search("uiassets/ui_emotechaticon/angryicon.png").group(3) == "angryicon"


def test_prefab_paths():
    assert ACTOR.match("actor/m.kfm").group(1) == "m"
    assert not ACTOR.match("actor/m_avatar.nif")
    assert WEAR.match("wear/m_head_001_type02.nif").group(1) == "m_head_001_type02"
    assert TILE.match("Map_04_02.unity3d").groups() == ("04", "02")
    assert not TILE.match("DongResources_04_02.resourceFile")


def test_archive_preference():
    assert preferred(["CharacterCreation.resourceFile", "CharacterSelection_wear_hat.resourceFile",
                      "CharacterSelection.resourceFile"])[:2] == [
        "CharacterSelection.resourceFile", "CharacterSelection_wear_hat.resourceFile"]
    order = models_preferred(["DongResources_04_02.resourceFile", "Tutorial.resourceFile",
                              "World_shared_part5.resourceFile", "Nano_001.resourceFile"])
    assert order == ["World_shared_part5.resourceFile", "Tutorial.resourceFile", "Nano_001.resourceFile",
                     "DongResources_04_02.resourceFile"]


def test_named_textures():
    xdt = {"m_pFaceItemTable": {
        "m_pItemData": [{"m_iMesh": 0}],
        "m_pItemMeshData": [{
            "m_pstrMMeshModelString": "m_face_001", "m_pstrMTextureString": "m_face_001",
            "m_pstrMTextureString2": "null", "m_pstrFMeshModelString": "null",
            "m_pstrFTextureString": "null", "m_pstrFTextureString2": "null"}],
    }}
    hnpc = [{"strHairTexture": "F_Head_014_a.dds", "strHatTextureM": "null", "iType": 47}]
    names = named_textures(xdt, hnpc)
    assert {"m_face_001_a", "m_face_001_e", "m_skin", "f_head_014_a"} <= names
    assert "null" not in names


def test_light_direction():
    # main.unity3d's "Directional light", the same in all three builds
    q = [0.19106532633304596, -0.7912864685058594, 0.31334972381591797, -0.4890519082546234]
    d = toward_light(q)
    assert [round(c, 4) for c in d] == [0.8937, 0.309, 0.3253]
    assert math.isclose(sum(c * c for c in d), 1, rel_tol=1e-5)
    # unrotated, a light shines along +z: towards it is -z, mirrored stays -z
    assert toward_light([0, 0, 0, 1]) == [-0.0, -0.0, -1.0]


def test_entry_is_a_tuple():
    e = entry("icons/cosicon_00.png", 28)
    assert STAGES["base"].seed(e)
    assert not STAGES["base"].seed(entry("icons/cosicon_00.png", 21))
    assert STAGES["world"].seed(entry("bgm/01 midtown.ogg", 83))
    assert STAGES["models"].seed(entry("mob/mob_spawn_wolf.kfm", 1))
    assert STAGES["models"].seed(entry("nano/nano_eddy.kfm", 4))
    assert not STAGES["models"].seed(entry("mob/mob_spawn_wolf.kfm", 21))
    assert STAGES["media"].seed(entry("vo/blossom_greet01.wav", 83))
    # the nano archives' skins aren't worn
    assert not STAGES["avatar"].seed(entry("texture/nano_eddy.dds", 28, "Nano_001.resourceFile"))
    assert STAGES["avatar"].seed(entry("texture/m_skin.dds", 28, "CharTexture.resourceFile"))
