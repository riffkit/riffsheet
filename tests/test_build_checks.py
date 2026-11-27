"""Unit tests for the checks `build` runs on a judgment, one check at a time, on hand-made state.
No video and no ffmpeg: each test builds the few parts of a BuildState the check reads."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from riffsheet_lib import build, report  # noqa: E402


def state(J=None, cuts=(3.0,), dur=6.0, events=(), panes=None, words=()):
    """A BuildState for a clip of `dur` seconds with cuts at `cuts`."""
    starts = [0.0] + list(cuts)
    ends = list(cuts) + [dur]
    idx = {
        "facts": {"duration_video_s": dur},
        "shots": [{"id": f"S{k + 1}", "start": a, "end": b} for k, (a, b) in enumerate(zip(starts, ends))],
        "events": list(events),
    }
    if panes is not None:
        idx["panes"] = panes
    return build.BuildState(idx, pts=[], words=list(words), J=J or {})


def prose(s, *segments):
    """Give the state prose segments: (start, end, text) each."""
    s.psegs = [{"window": [a, b], "text": t} for a, b, t in segments]
    s.prose = "\n\n".join(t for _, _, t in segments)
    return s


def voice(vid, start, mode="on_camera_dialogue", speaker="protagonist", band="measured"):
    return {"id": vid, "time_range": [start, start + 1], "mode": mode, "speaker": speaker, "_pace": {"band": band}}


def word(w, start, end):
    return {"word": w, "start": start, "end": end}


class Lines(unittest.TestCase):
    def test_speaking_mode(self):
        self.assertEqual(build.speaking_mode([]), "none")
        self.assertEqual(build.speaking_mode([voice("vs1", 0, mode="no_dialogue")]), "none")
        self.assertEqual(build.speaking_mode([voice("vs1", 0)]), "on_camera")
        self.assertEqual(build.speaking_mode([voice("vs1", 0, mode="voiceover")]), "voiceover")
        self.assertEqual(build.speaking_mode([voice("vs1", 0), voice("vs2", 2, mode="voiceover")]), "mixed")

    def test_sentence_end_or_comma_before_a_pause_is_warned(self):
        ws = [word(" One.", 0.0, 0.3), word(" Two,", 0.6, 0.9), word(" three", 1.2, 1.5), word(" four", 1.55, 1.8)]
        out = build.sentence_pause_warnings(1, 10, ws)
        self.assertEqual(len(out), 2)
        self.assertIn("'One.' (word 10) ends a sentence", out[0])
        self.assertIn("'Two,' (word 11) is followed by a 0.30 s pause", out[1])

    def test_a_word_belongs_to_one_line_and_is_not_music(self):
        ws = [word(f" w{i}", i * 0.3, i * 0.3 + 0.2) for i in range(6)]
        s = state(J={"lines": [{"words": "0-2"}, {"words": "2-3"}], "music_words": [{"words": "3-5"}]}, words=ws)
        build.check_words_used_once(s)
        self.assertEqual(s.problems, ["word 2 is in both vs1 and vs2", "word 3 is both a spoken line (vs2) and music"])


class Prose(unittest.TestCase):
    def test_cut_is_a_boundary_or_named(self):
        s = prose(state(), (0.0, 6.0, "[00:00.0-00:06.0] Bars stand."))
        build.check_cuts_named(s)
        self.assertEqual(s.problems, ["cut at 3.000 is neither a segment boundary nor named (00:03.0) in its segment"])
        for named in ("[00:00.0-00:06.0] Bars stand; at 00:03.0 the picture cuts.", "Cut at 00:02.9."):
            s = prose(state(), (0.0, 6.0, named))
            build.check_cuts_named(s)
            self.assertEqual(s.problems, [], named)
        s = prose(state(), (0.0, 3.05, "a"), (3.05, 6.0, "b"))  # a boundary within 0.1 s
        build.check_cuts_named(s)
        self.assertEqual(s.problems, [])

    def test_panel_change_is_named(self):
        ev = {"id": "E1", "kind": "panel", "t": 1.5}
        s = prose(state(cuts=(), events=[ev]), (0.0, 6.0, "Two panes."))
        build.check_panel_changes_named(s)
        self.assertEqual(len(s.problems), 1)
        self.assertIn("E1 panel change at 1.500", s.problems[0])
        s = prose(state(cuts=(), events=[ev]), (0.0, 6.0, "Two panes; at 00:01.5 the lower one cuts."))
        build.check_panel_changes_named(s)
        self.assertEqual(s.problems, [])

    def test_ascii_double_quote(self):
        s = prose(state(), (0.0, 6.0, 'She says "hi".'))
        build.check_prose_quotes(s)
        self.assertEqual(s.problems, ["prose contains the ASCII double-quote character"])

    def test_image_marker_names_an_entity(self):
        s = prose(state(), (0.0, 6.0, "[image:host] waves to [image:ghost]."))
        s.ents = [{"id": "host", "kind": "person", "params": {}}]
        build.check_image_markers(s)
        self.assertEqual(s.problems, ["[image:ghost] names no person or source_image entity"])

    def test_entities_appear_and_are_labeled(self):
        s = prose(state(), (0.0, 6.0, "[image:host] talks."))
        s.ents = [
            {"id": "host", "kind": "person", "params": {}},
            {"id": "guest", "kind": "person", "params": {}},
            {"id": "mug", "kind": "source_image", "params": {}},
            {"id": "cap", "kind": "subtitle", "params": {"voice_anchor": "vs9", "visual_anchor": "lamp"}},
        ]
        s.ids = {e["id"] for e in s.ents}
        build.check_entities(s)
        self.assertEqual(len(s.problems), 4, s.problems)
        self.assertIn("person guest never appears as [image:guest] in prose", s.problems)
        self.assertTrue(s.problems[1].startswith("object mug: no caption names it as visual_anchor"))
        self.assertIn("cap: voice_anchor vs9 is not a voice segment", s.problems)
        self.assertIn("cap: visual_anchor lamp is not an entity", s.problems)


class VoiceMarkers(unittest.TestCase):
    def run_check(self, vsegs, *segments, ents=()):
        s = prose(state(), *segments)
        s.vsegs = list(vsegs)
        s.ents = [{"id": e, "kind": "person", "params": {}} for e in ents]
        build.check_voice_markers(s)
        return s.problems

    def test_once_in_the_segment_where_the_line_starts(self):
        self.assertEqual(self.run_check([voice("vs1", 1.0, speaker="narrator")], (0.0, 6.0, "A [voice:vs1].")), [])
        twice = self.run_check([voice("vs1", 1.0, speaker="narrator")], (0.0, 6.0, "[voice:vs1] and [voice:vs1]."))
        self.assertEqual(twice, ["[voice:vs1] appears 2 times in prose (must be once)"])
        late = self.run_check([voice("vs1", 1.0, speaker="narrator")], (0.0, 3.0, "a"), (3.0, 6.0, "b [voice:vs1]"))
        self.assertEqual(len(late), 1)
        self.assertIn("[voice:vs1] is in segment 2, but the line starts at 1.000, inside segment 1", late[0])

    def test_no_dialogue_has_no_marker(self):
        p = self.run_check([voice("vs1", 1.0, mode="no_dialogue")], (0.0, 6.0, "[voice:vs1]"))
        self.assertEqual(p, ["[voice:vs1] in prose but the line is no_dialogue"])

    def test_speaker_marker_stands_before_it(self):
        segs = (0.0, 6.0, "[image:guest] nods, then [voice:vs1].")
        self.assertEqual(
            self.run_check([voice("vs1", 1.0, speaker="host")], segs, ents=("host", "guest")),
            ["[voice:vs1]: nearest marker to its left is guest, speaker is host"],
        )
        self.assertEqual(
            self.run_check([voice("vs1", 1.0, speaker="host")], (0.0, 6.0, "[voice:vs1]"), ents=("host",)),
            ["[voice:vs1]: no [image:X] marker before it in its segment"],
        )
        self.assertEqual(
            self.run_check([voice("vs1", 1.0, speaker="stranger")], (0.0, 6.0, "[voice:vs1]")),
            ["vs1: speaker stranger is not protagonist, narrator or a person entity"],
        )

    def test_pace_word_is_the_measured_band(self):
        s = prose(state(), (0.0, 6.0, "She speaks in a brisk voice [voice:vs1]. Then a measured pause."))
        s.vsegs = [voice("vs1", 1.0, band="measured")]
        build.check_pace_words(s)
        self.assertEqual(s.problems, ["[voice:vs1]: its sentence says brisk; measured pace is measured"])

    def test_voice_marker_names_a_line(self):
        s = prose(state(), (0.0, 6.0, "[voice:vs2]"))
        build.check_voice_ids(s)
        self.assertEqual(
            s.problems, ["[voice:vs2] names no voice segment", "speaking_mode none but prose has [voice:X]"]
        )


class Words(unittest.TestCase):
    def test_id_written_as_a_plain_word(self):
        s = prose(state(J={"report": {"what_happens": "woman_1 laughs", "swappable": ["the protagonist"]}}))
        s = prose(s, (0.0, 6.0, "[image:woman_1] smiles; woman_1 waves."))
        s.ents = [{"id": "woman_1", "kind": "person", "params": {}}]
        build.check_ids_as_words(s)
        self.assertEqual(len(s.problems), 3, s.problems)
        self.assertTrue(s.problems[0].startswith("report: the id 'protagonist'"))
        self.assertTrue(s.problems[1].startswith("prose: the id 'woman_1' is written as a plain word"))
        self.assertTrue(s.problems[2].startswith("report: the id 'woman_1'"))

    def test_one_garment_one_color_name(self):
        J = {"segments": [{"text": "a gray shirt"}], "people": [{"id": "p", "semantic": "in a blue shirt"}]}
        s = state(J=J)
        build.check_garment_color_names(s)
        self.assertEqual(len(s.warnings), 1)
        self.assertTrue(s.warnings[0].startswith("'shirt' is called "), s.warnings[0])

    def test_voiceover_named_in_the_summary(self):
        lines = [{"mode": "on_camera_dialogue"}, {"mode": "voiceover"}]
        s = state(J={"lines": lines, "report": {"what_happens": "She talks to camera."}})
        build.check_voiceover_in_summary(s)
        self.assertEqual(len(s.warnings), 1)
        self.assertTrue(s.warnings[0].startswith("report what_happens: vs2 is voiceover"))
        s = state(J={"lines": lines, "report": {"what_happens": "She talks, then a voice-over explains."}})
        build.check_voiceover_in_summary(s)
        self.assertEqual(s.warnings, [])

    def test_color_no_measurement_could_be(self):
        s = state(cuts=())
        s.pts = [0.0, 1.0, 2.0]
        s.idx["followups"] = [
            {"cmd": "color", "frames": [1], "box": [0.1, 0.1, 0.3, 0.3], "colors": [{"name": "dark green"}]}
        ]
        s.confirmed = [{"where": "segment 1", "words": "a red shirt", "view": "shot_01", "t": 1.0, "box": None}]
        build.check_measured_colors(s)
        self.assertEqual(len(s.warnings), 1)
        self.assertIn("'a red shirt' says red, but no `color` measurement in the same shot could be red", s.warnings[0])
        s.warnings = []
        s.confirmed[0]["words"] = "a green shirt"
        build.check_measured_colors(s)
        self.assertEqual(s.warnings, [])


class Slots(unittest.TestCase):
    def slot(self, sid, a, b, stage):
        return {"id": sid, "time_range": [a, b], "formula": {"funnel_stage": stage}}

    def test_slots(self):
        s = prose(state(J={"segments": [1], "slots": [1]}), (0.0, 3.0, "a"), (3.0, 6.0, "b"))
        s.slots = [self.slot("s1", 0.0, 2.0, "hook"), self.slot("s2", 2.0, 5.0, "hook")]
        build.check_slots(s)
        self.assertEqual(
            s.problems,
            [
                "two slots share a funnel_stage",
                "s1 ends at 2.0 which is not a prose segment boundary",
                "last slot must end at 'end'",
            ],
        )
        s = prose(state(J={"segments": [1], "slots": [1]}), (0.0, 6.0, "a"))
        s.slots = [self.slot(f"s{k}", k, k + 1, str(k)) for k in range(5)]
        build.check_slots(s)
        self.assertIn("5 slots (at most 4)", s.problems)
        s = state()
        build.check_slots(s)
        self.assertEqual(s.problems, ["no segments yet", "no slots yet"])

    def test_formula_keys_and_slot_order(self):
        J = {"slots": [{"to": 3.0, "formula": {"meaning_contract": {"x": 1}}}, {"to": 2.0, "formula": {}}]}
        s = state(J=J)
        s.jj = build.Judgment(None, s.idx, [], [])
        build.build_slots(s)
        self.assertTrue(s.problems[0].startswith("s1: formula missing funnel_stage, function"))
        self.assertEqual(s.problems[1], "s1: meaning_contract needs attention_contract, payoff_meaning, proof_surface")
        self.assertEqual(s.problems[3], "s2: ends at 2.0 which is not after its start 3.0" + build.TO_HINT)

    def test_to_names_where_it_ends(self):
        """`to` is an end: "S1" is the start of shot 1, so a slot given "to": "S1" is empty, and the problem
        says how to name the end of shot 1 (a first-time agent read "S1" as "through shot 1")."""
        J = {"slots": [{"to": "S1", "formula": {}}, {"to": "end", "formula": {}}]}
        s = state(J=J)
        s.jj = build.Judgment(None, s.idx, [], [])
        build.build_slots(s)
        empty = [p for p in s.problems if "not after its start" in p]
        self.assertEqual(empty, ["s1: ends at 0.0 which is not after its start 0.0" + build.TO_HINT])
        self.assertIn("ends at S(n+1) or Sn.end", build.TO_HINT)
        J["slots"][0]["to"] = "S1.end"
        s = state(J=J)
        s.jj = build.Judgment(None, s.idx, [], [])
        build.build_slots(s)
        self.assertFalse([p for p in s.problems if "not after its start" in p])


class VideoFormat(unittest.TestCase):
    def test_format_name_and_split_graphic(self):
        s = state(J={"video_format": "two_up"})
        build.check_video_format(s)
        self.assertTrue(s.problems[0].startswith("video_format 'two_up' is not one of single_shot"))
        s = state(J={"video_format": "split_screen_top_bottom", "graphics": [{"split": True}]})
        build.check_video_format(s)
        self.assertTrue(s.problems[0].startswith("video_format split_screen_top_bottom with a split graphic"))

    def test_measured_split_must_be_accounted_for(self):
        pane = {"id": "P1", "axis": "top/bottom", "seam": 0.5, "on": 0.0, "off": 6.0}
        s = state(panes=[pane])
        build.check_video_format(s)
        self.assertEqual(len(s.problems), 1)
        self.assertIn("P1: the frame is split top/bottom at 0.500", s.problems[0])
        self.assertIn("video_format split_screen_top_bottom", s.problems[0])
        for J in ({"video_format": "split_screen_top_bottom"}, {"graphics": [{"split": True}]}):
            s = state(J=J, panes=[pane])
            build.check_video_format(s)
            self.assertEqual(s.problems, [], J)

    def test_language_needed(self):
        s = state()
        build.build_metadata(s)
        self.assertEqual(
            s.problems, ["language unknown: no transcript language; give 'language' (on-screen text language)"]
        )
        s = state(J={"language": "en"})
        build.build_metadata(s)
        self.assertEqual((s.problems, s.meta["language"], s.meta["_src"]["language"]), ([], "en", "seen"))


class Report(unittest.TestCase):
    def test_checks_line(self):
        self.assertEqual(build.checks_line(0, 0), "CHECKS: all passed")
        self.assertEqual(build.checks_line(2, 0), "CHECKS: 2 problem(s)")
        self.assertEqual(build.checks_line(0, 3), "CHECKS: 3 problem(s), all under UNCONFIRMED below")
        self.assertEqual(build.checks_line(2, 3), "CHECKS: 5 problem(s): 2 listed here, 3 under UNCONFIRMED below")

    def test_mmss_rounds_before_splitting_minutes(self):
        from riffsheet_lib.util import mmss

        self.assertEqual(
            [mmss(t) for t in (0, 2.0, 59.94, 59.97, 61.26, -1)],
            ["00:00.0", "00:02.0", "00:59.9", "01:00.0", "01:01.3", "00:00.0"],
        )

    def test_size_class(self):
        self.assertIsNone(build.size_class(None, "abc"))
        self.assertEqual(build.size_class(60, "ABC"), "medium")  # capitals: letters = row height
        self.assertEqual(build.size_class(60, "ace"), "small")  # 60 / 1.2 = 50
        self.assertEqual(build.size_class(200, "jog"), "very_large")  # 200 / 1.4 = 143


class Headline(unittest.TestCase):
    """The line under the report's title names the speech's language, and with no speech only the
    on-screen text's language the agent gave."""

    def meta(self, mode, lang, src):
        return {
            "duration_seconds": 12.0,
            "video_format": "single_shot",
            "speaking_mode": mode,
            "language": lang,
            "_src": {"language": src},
        }

    def test_language_follows_the_speech(self):
        line = report.headline(self.meta("on_camera", "es", "measured"), 4, 5)
        self.assertEqual(line, "12.0 s · 4 shots · one picture at a time · spoken on camera (es) · 5 spoken lines")

    def test_no_speech_names_the_text_language_only(self):
        seen = report.headline(self.meta("none", "en", "seen"), 5, 0)
        self.assertEqual(seen, "12.0 s · 5 shots · one picture at a time · no speech · on-screen text in en")
        guessed = report.headline(self.meta("none", "ko", "measured"), 1, 0)
        self.assertEqual(guessed, "12.0 s · 1 shot · one picture at a time · no speech")


if __name__ == "__main__":
    unittest.main()
