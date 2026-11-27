"""What `build` writes and refuses, run on the main clip's scan."""

import json
import os
import shlex
import sys
import unittest

from tests import clips
from tests.clips import CLIPS, ROOT, TOOL, MainClipCase, cs, index, judgment, ok, read, refused, scan

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
import riffsheet_lib  # noqa: E402
import riffsheet_lib.build  # noqa: E402
import riffsheet_lib.details  # noqa: E402
import riffsheet_lib.report  # noqa: E402
import riffsheet_lib.schema  # noqa: E402
import riffsheet_lib.sheets  # noqa: E402


def setUpModule():
    clips.setUpModule()


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = scan("main", "--transcript", CLIPS["main_transcript"])
        for args in (
            ("text", cls.d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap"),
            ("element", cls.d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red"),
        ):
            r = cs(*args)
            if r.returncode:
                raise RuntimeError(r.stderr)
        with open(os.path.join(cls.d, "look", "cap.json"), encoding="utf-8") as f:
            states = json.load(f)["states"]
        cls.ids = [next(s["id"] for s in states if s["on"] == t) for t in (2.3, 3.0)]

    def write(self, name, detail):
        p = os.path.join(clips.WORK, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(judgment(detail, *self.ids), f)
        return p

    def test_refuses_unconfirmed_detail(self):
        out = os.path.join(clips.WORK, "build refused")
        r = cs("build", self.d, "--judgment", self.write("j1.json", "Bars stand on a table."), "--out", out)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("UNCONFIRMED", r.stdout)
        self.assertIn("table", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(out, "riffsheet.json")))
        self.assertFalse(os.path.exists(os.path.join(out, "riffsheet.md")))

    def test_passes_confirmed_detail_and_is_repeatable(self):
        j = self.write("j2.json", "Bars stand on a {table|shot_02}.")
        outs = []
        for k in (1, 2):
            out = os.path.join(clips.WORK, f"build {k}")
            r = cs("build", self.d, "--judgment", j, "--out", out)
            ok(self, r)
            outs.append(out)
        for f in ("riffsheet.json", "riffsheet.md"):
            with open(os.path.join(outs[0], f), "rb") as a, open(os.path.join(outs[1], f), "rb") as b:
                self.assertEqual(a.read(), b.read(), f + " differs between two runs")
        with open(os.path.join(outs[0], "riffsheet.json"), encoding="utf-8") as f:
            A = json.load(f)
        self.assertEqual(A["format_version"], riffsheet_lib.FORMAT_VERSION)
        self.assertEqual(riffsheet_lib.schema.validate(A, riffsheet_lib.schema.ANALYSIS_SCHEMA), [])
        self.assertEqual([c["view"] for c in A["_local"]["confirmations"]], ["shots/shot_02.jpg"])
        self.assertNotIn("{", A["prose"])
        cap = [e for e in A["scene_entities"] if e["kind"] == "subtitle"][0]
        self.assertEqual(cap["time_range"], [2.3, 3.7])
        g = [e for e in A["scene_entities"] if e["kind"] == "graphic"][0]
        self.assertEqual(g["time_range"], [4.5, 5.5])
        self.assertEqual(A["audio"]["voice_segments"][0]["time_range"], [2.3, 3.4])
        # the report reads as an account: beats in order, the spoken line in quotes, no markers or ids
        md = read(os.path.join(outs[0], "riffsheet.md"))
        self.assertIn("## Beat by beat", md)
        self.assertIn("\u201chello world\u201d", md)
        self.assertNotIn("[voice:", md)
        self.assertNotIn("[image:", md)
        self.assertIn("**Keep when remaking.**", md)
        # where sound events fall on the cuts and the caption's appearance: measured, not heard
        sp = A["_local"]["sound_at_picture"]
        self.assertEqual([c["span"] for c in sp["cuts"]["changes"]], [[2.0, 2.0], [4.0, 4.0]])
        self.assertTrue(sp["cuts"]["summary"].startswith("0 of 2 cuts land on a loudness peak or rise"))
        self.assertEqual([(c["id"], c["span"]) for c in sp["captions"]["changes"]], [(cap["id"], [2.3, 2.3])])
        self.assertIn("Sound and picture (measured times, not what the sound is): 0 of 2 cuts", md)

    def test_zoom_view_named_with_or_without_jpg(self):
        # a zoom name carries times and a box (zoom_3.00_10-20-60-70): its dots are not an extension
        ok(self, cs("zoom", self.d, "--at", "3.0", "--box", "0.1,0.2,0.6,0.7"))
        z = [f for f in index(self.d)["followups"] if f.get("cmd") == "zoom"][-1]
        name = os.path.basename(z["images"][0]["path"])
        self.assertTrue(name.endswith(".jpg") and "." in name[:-4], name)
        for k, ref in enumerate((name[:-4], name)):
            j = self.write(f"j_zoom{k}.json", "Bars stand on a {table|%s}." % ref)
            out = os.path.join(clips.WORK, f"build zoom {k}")
            ok(self, cs("build", self.d, "--judgment", j, "--out", out))
            with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
                A = json.load(f)
            self.assertEqual([c["view"] for c in A["_local"]["confirmations"]], [z["images"][0]["path"]])

    def test_scan_is_repeatable(self):
        d2 = os.path.join(clips.WORK, "scan main again")
        ok(self, cs("scan", CLIPS["main"], "--out", d2, "--transcript", CLIPS["main_transcript"]))
        a, b = index(self.d), index(d2)
        for x in (a, b):
            x.pop("scan_seconds")
            x.pop("followups", None)
        self.assertEqual(a, b)
        for root, _, files in os.walk(d2):
            for f in files:
                if f.endswith((".jpg", ".json")) and f != "index.json":
                    rel = os.path.relpath(os.path.join(root, f), d2)
                    with open(os.path.join(d2, rel), "rb") as x, open(os.path.join(self.d, rel), "rb") as y:
                        self.assertEqual(x.read(), y.read(), rel)

    def test_output_that_breaks_the_format_is_not_written(self):
        j = judgment("Bars stand on a {table|shot_02}.", *self.ids)
        j["graphics"][0]["description"] = 7  # must be text
        p = os.path.join(clips.WORK, "j3.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(j, f)
        out = os.path.join(clips.WORK, "build bad")
        r = cs("build", self.d, "--judgment", p, "--out", out)
        refused(self, r, "does not fit the format", "description")
        self.assertFalse(os.path.exists(os.path.join(out, "riffsheet.json")))


class BuildChecks(unittest.TestCase):
    """What `build` says about the judgment: ordinary phrases are not details, movements need frames,
    misplaced markers and objects are named plainly, the report reads as plain words."""

    @classmethod
    def setUpClass(cls):
        cls.d = scan("main", "--transcript", CLIPS["main_transcript"])
        for args in (
            ("text", cls.d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap"),
            ("element", cls.d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red"),
            ("frames", cls.d, "--from", "2.3", "--to", "2.6", "--name", "moves"),
        ):
            r = cs(*args)
            if r.returncode:
                raise RuntimeError(r.stderr)
        with open(os.path.join(cls.d, "look", "cap.json"), encoding="utf-8") as f:
            states = json.load(f)["states"]
        cls.ids = [next(s["id"] for s in states if s["on"] == t) for t in (2.3, 3.0)]

    def build(self, name, detail="Bars stand still.", edit=None):
        j = judgment(detail, *self.ids)
        if edit:
            edit(j)
        p = os.path.join(clips.WORK, name + ".json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(j, f)
        out = os.path.join(clips.WORK, "build " + name)
        return cs("build", self.d, "--judgment", p, "--out", out), out

    def test_ordinary_phrases_are_not_details(self):
        r, _ = self.build(
            "plain",
            "Bars stand still under soft window light and a ring light glow; the pauses fall "
            "to near silence (no music bed), and the caption sits on the bars.",
        )
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)

    def test_supports_and_products_still_need_a_view(self):
        r, _ = self.build("support", "A bottle rests on a shelf; a jar sits on the table.")
        self.assertEqual(r.returncode, 3, r.stdout)
        for w in ("bottle", "rests on", "shelf", "jar", "table"):
            self.assertIn(w, r.stdout)

    def test_movement_needs_a_frames_view(self):
        r, _ = self.build("nod_bare", "The bars nod twice.")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("movement words outside a {words|view} mark: nod", r.stdout)
        r, _ = self.build("nod_still", "The {bars nod twice|shot_02}.")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("cannot show a movement", r.stdout)
        r, _ = self.build("nod_frames_detail", "The {bars nod on a table|moves}.")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("too small for table", r.stdout)
        r, out = self.build("nod_frames", "The {bars nod twice|moves}.")
        ok(self, r)
        with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
            self.assertEqual([c["view"] for c in json.load(f)["_local"]["confirmations"]], ["look/moves.jpg"])
        self.assertIn("VIEWS NAMED in detail marks (1): look/moves.jpg", r.stdout)

    def test_object_needs_a_caption_that_labels_it(self):
        def edit(j):
            j["objects"] = [{"id": "bars", "semantic": "color bars", "time": ["S2", "S2.end"], "description": "bars"}]
            j["segments"][1]["text"] = "[image:bars] stand still. " + j["segments"][1]["text"]

        r, _ = self.build("object", edit=edit)
        self.assertIn("object bars: no caption names it as visual_anchor", r.stdout)

        def labeled(j):
            edit(j)
            j["captions"][0]["visual_anchor"] = "bars"

        r, _ = self.build("object_labeled", edit=labeled)
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)

    def test_voice_marker_in_the_wrong_segment_is_named_once(self):
        def edit(j):
            j["segments"][1]["text"] = "Bars stand still; a hard cut at 00:04.0."
            j["segments"][2]["text"] = "Cells swarm; the voice says hello world [voice:vs1]."

        r, _ = self.build("voice", edit=edit)
        self.assertIn("[voice:vs1] is in segment 3, but the line starts at 2.300, inside segment 2", r.stdout)
        self.assertNotIn("nearest marker", r.stdout)

    def test_id_as_a_plain_word_and_counts(self):
        r, _ = self.build("ids", "The protagonist waits by a table.")
        self.assertIn("the id 'protagonist' is written as a plain word", r.stdout)
        self.assertIn("CHECKS: 2 problem(s): 1 listed here, 1 under UNCONFIRMED below", r.stdout)

    def test_one_garment_two_color_names_warned(self):
        def edit(j):
            j["segments"][2]["text"] = "Cells swarm while a red block shows; {a blue shirt|shot_03} hangs."

        r, _ = self.build("colors", "Bars stand beside {a pale gray ribbed shirt|shot_02}.", edit)
        ok(self, r)
        self.assertIn("'shirt' is called blue (segment 3); gray (segment 2)", r.stdout)

    def test_report_words(self):
        def edit(j):
            j["slots"][0]["formula"]["funnel_stage"] = "cta"

        r, out = self.build("report", edit=edit)
        ok(self, r)
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("### 1. Call to action · ", md)
        self.assertIn("Captions of the spoken words: \u201cHELLO WORLD\u201d (00:02.3\u201300:03.7).", md)

    def test_mouth_takes_a_word_range(self):
        r = cs("mouth", self.d, "--box", "0.3,0.3,0.7,0.5", "--words", "0-1")
        ok(self, r)
        self.assertIn("mouth: ", r.stdout)
        self.assertIn("hello[2.30-2.60]", r.stdout)
        self.assertIn("world[3.00-3.40]", r.stdout)

    def test_summary_prints_next_once(self):
        lines = read(os.path.join(self.d, "summary.txt")).splitlines()
        self.assertEqual(sum(1 for x in lines if x.startswith("NEXT")), 1)


class DetailMarks(MainClipCase):
    """Which words are details, which views confirm them, and the names views are given."""

    def test_any_movement_may_name_a_frames_sheet(self):
        r, out = self.build("sway_frames", "The {bars sway left and right twice|moves}.")
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)
        with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
            self.assertEqual([c["view"] for c in json.load(f)["_local"]["confirmations"]], ["look/moves.jpg"])
        r, _ = self.build("sway_frames_detail", "The {bars sway beside a mug|moves}.")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("too small for mug", r.stdout)

    def test_holds_without_an_object_is_not_a_detail(self):
        r, _ = self.build("holds_plain", "The picture holds still and the top band holds.")
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)
        r, _ = self.build("holds_object", "A hand holds a sign; another is holding it up.")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("detail words outside a {words|view} mark: holding, holds", r.stdout)

    def test_holding_something_abstract_is_not_a_detail(self):
        for t in (
            "keeps that gaze",
            "holds that gaze",
            "holds the pose",
            "holds the viewer's attention",
            "holds a note",
            "held her gaze",
            "holds her smile for a beat",
        ):
            self.assertEqual(riffsheet_lib.details.detail_hits(t), [], t)
        for t, hit in (
            ("holds a mug", ["holds", "mug"]),
            ("holds a notebook", ["holds"]),
            ("holding it up", ["holding"]),
        ):
            self.assertEqual(riffsheet_lib.details.detail_hits(t), hit, t)

    def test_each_image_states_its_mark_name(self):
        r = cs("zoom", self.d, "--at", "2.5", "--at", "3.2", "--box", "0.1,0.2,0.6,0.7")
        ok(self, r)
        z = [f for f in index(self.d)["followups"] if f.get("cmd") == "zoom"][-1]
        names = [riffsheet_lib.details.view_name(im["path"]) for im in z["images"]]
        for nm, im in zip(names, z["images"]):
            self.assertTrue(im["times"])
            for t in im["times"]:
                self.assertIn("{words|%s@%.3f}" % (nm, t), r.stdout)
        r = cs("zoom", self.d, "--at", "5.0")
        ok(self, r)
        self.assertIn("in a mark: {words|zoom_5.00}", r.stdout)
        # a long window fills several pages: each page is named with its suffix and the frames it shows
        r = cs("frames", self.d, "--from", "0", "--to", "6")
        ok(self, r)
        f = [x for x in index(self.d)["followups"] if x.get("cmd") == "frames"][-1]
        self.assertGreater(len(f["images"]), 1)
        for k, im in enumerate(f["images"], 1):
            nm = riffsheet_lib.details.view_name(im["path"])
            self.assertTrue(nm.endswith("_%02d" % k), nm)
            self.assertIn("in a mark: {movement words|%s} (frames " % nm, r.stdout)
        # a page of a zoom confirms only the moments it shows
        imgs = [{"cells": 2}, {"cells": 1}]
        self.assertEqual(riffsheet_lib.sheets.page_times(imgs, [1.0, 2.0, 3.0]), [[1.0, 2.0], [3.0]])

    def test_detail_words_are_published_before_the_first_build(self):
        r = cs("build", self.d)
        ok(self, r)
        self.assertIn("DETAIL WORDS (references/TOOL.md, section 'Detail words')", r.stdout)
        for w in ("outfit", "counter", "room", "window", "café", "lamp", "holds that gaze"):
            self.assertIn(w, r.stdout)
        # the list in the tool reference is the list the tool uses
        tool = read(os.path.join(ROOT, "references", "TOOL.md"))
        sec = tool.split("## Detail words", 1)[1].split("\n## ", 1)[0]
        listed = set()
        for ln in sec.splitlines():
            if ln.startswith("- ") and ":" in ln:
                body = ln.split(":", 1)[1].split("; and hold", 1)[0]
                listed |= {w.strip().rstrip(".") for w in body.split(",") if w.strip()}
        self.assertEqual(listed, set(riffsheet_lib.details.DETAIL_WORDS))
        for w in riffsheet_lib.details.HOLD_ABSTRACT:
            self.assertIn(w, sec)


class ColorWarnings(MainClipCase):
    """Color words a `color` measurement of the same shot contradicts are warned about, one word at a time."""

    def test_color_a_measurement_contradicts_is_warned(self):
        r = cs("color", self.d, "--at", "5.0", "--box", "0.13,0.17,0.31,0.24")
        ok(self, r)
        self.assertIn("red", r.stdout)

        def blue(j):
            j["segments"][2]["text"] = "Cells swarm while {a blue block|shot_03} shows."

        r, _ = self.build("color_blue", edit=blue)
        ok(self, r)
        self.assertIn(
            "'a blue block' says blue, but no `color` measurement in the same shot could be blue: it measured red",
            r.stdout,
        )

        def red(j):
            j["segments"][2]["text"] = "Cells swarm while {a red block|shot_03} shows."

        r, _ = self.build("color_red", edit=red)
        ok(self, r)
        self.assertNotIn("says red", r.stdout)

    def test_each_color_word_is_checked(self):
        def two(j):
            j["segments"][2]["text"] = "Cells swarm while {a red and green block|shot_03} shows."

        r, _ = self.build("color_two", edit=two)
        ok(self, r)
        self.assertIn("'a red and green block' says green, but no `color` measurement", r.stdout)
        self.assertNotIn("says red", r.stdout)

        def metal(j):
            j["segments"][2]["text"] = "Cells swarm while {a red block with gold trim|shot_03} shows."

        r, _ = self.build("color_metal", edit=metal)
        ok(self, r)
        self.assertNotIn("but no `color` measurement", r.stdout)


class PaceAndMessages(MainClipCase):
    """Pace before and after a spelling fix, and the commands and window messages the tool prints."""

    def test_pace_on_the_sheet_before_any_judgment(self):
        r = cs("build", self.d)
        ok(self, r)
        self.assertIn("PACE (measured, per sentence", r.stdout)
        self.assertIn("  0-1: unhurried, 1.82 words/s  | hello world", r.stdout)

    def test_pace_counted_on_the_corrected_line(self):
        ws = [
            {"start": 0.0, "end": 0.4, "word": " This"},
            {"start": 0.4, "end": 0.6, "word": " is"},
            {"start": 0.6, "end": 0.8, "word": " Rift"},
            {"start": 0.8, "end": 1.0, "word": " Kit."},
        ]
        self.assertEqual(riffsheet_lib.build.pace_of(ws)["count"], 4)
        self.assertEqual(riffsheet_lib.build.pace_of(ws, "This is Riffkit.")["count"], 3)
        self.assertEqual(riffsheet_lib.build.pace_of(ws, "This is Riffkit.")["band"], "measured")  # 3.0 words/s
        self.assertEqual(riffsheet_lib.build.pace_of(ws)["band"], "brisk")  # 4.0 words/s

        def joined(j):
            j["lines"][0]["fix"] = {"hello world": "helloworld"}
            j["segments"][1]["text"] = "Bars stand still. The voice says helloworld [voice:vs1]; a hard cut at 00:04.0."

        r, out = self.build("pace_fixed", edit=joined)
        ok(self, r)
        with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
            pace = json.load(f)["audio"]["voice_segments"][0]["_pace"]
        self.assertEqual((pace["count"], pace["per_s"]), (1, 0.91))
        self.assertIn("0.91 words/s = unhurried", r.stdout)

    def test_printed_commands_use_the_running_python(self):
        summary = read(os.path.join(self.d, "summary.txt"))
        self.assertIn(shlex.quote(sys.executable) + " -I " + shlex.quote(TOOL) + " text ", summary)
        self.assertNotIn("\n  python3 -I ", summary)

    def test_window_edge_message_allows_a_caption_already_gone(self):
        r = cs("text", self.d, "--box", "0.05,0.75,0.95,0.88", "--from", "2.0", "--to", "2.8", "--name", "cap_short")
        ok(self, r)
        self.assertIn("runs past the window: if it shows a caption, its off time is not measured", r.stdout)


class ReportWording(MainClipCase):
    """The wording of riffsheet.md: plain names, quotes, articles, voiceover named, merged items."""

    def test_report_wording(self):
        def edit(j):
            j["lines"] = [{"words": "0-1", "mode": "voiceover", "speaker": "narrator", "fix": {"world": "world."}}]
            j["people"] = [
                {
                    "id": "protagonist",
                    "semantic": "a person",
                    "time": [0, "end"],
                    "attributes": {"role": "protagonist"},
                },
                {
                    "id": "supporting_a",
                    "semantic": "another person",
                    "time": [0, "end"],
                    "attributes": {"role": "supporting"},
                },
            ]
            j["segments"][0]["text"] = "[image:supporting_a] waves; a hard cut at 00:02.0."
            j["segments"][1]["text"] = (
                "[image:protagonist] stands by {a oatmeal wall|shot_02}; [image:supporting_a] waits. "
                "The voice says hello world [voice:vs1]; a hard cut at 00:04.0."
            )
            j["segments"][2]["text"] = "[image:supporting_a] and [image:protagonist] watch while a red block shows."
            j["graphics"][0]["inline_text"] = {"label": "GO NOW"}
            j["report"]["what_happens"] = "A oatmeal wall, a one-off shot and a uniform look."

        r, out = self.build("wording", edit=edit)
        ok(self, r)
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("An oatmeal wall, a one-off shot and a uniform look.", md)
        self.assertIn("by an oatmeal wall", md)
        self.assertIn("“hello world.”;", md)
        self.assertNotIn("”.", md)
        self.assertIn("A second person waves", md)
        self.assertIn("The video's main person stands", md)
        self.assertIn("the second person waits", md)
        self.assertIn("The second person and the main person watch", md)
        self.assertEqual(md.count("a second person") + md.count("A second person"), 1)
        self.assertIn("a marker: “GO NOW” (", md)

    def test_voiceover_missing_from_the_summary_is_warned(self):
        tr = os.path.join(clips.WORK, "two line transcript.json")
        with open(tr, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "language": "en",
                    "segments": [
                        {
                            "start": 2.3,
                            "end": 3.4,
                            "text": "hello. world.",
                            "words": [
                                {"start": 2.3, "end": 2.6, "word": " hello.", "prob": 0.9},
                                {"start": 3.0, "end": 3.4, "word": " world.", "prob": 0.9},
                            ],
                        }
                    ],
                },
                f,
            )
        d = os.path.join(clips.WORK, "scan two lines")
        ok(self, cs("scan", CLIPS["main"], "--out", d, "--transcript", tr))
        ok(self, cs("text", d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap"))
        ok(self, cs("element", d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red"))
        j = judgment("Bars stand still.", *self.ids)
        j["lines"] = [
            {"words": "0-0", "mode": "on_camera_dialogue", "speaker": "narrator"},
            {"words": "1-1", "mode": "voiceover", "speaker": "narrator"},
        ]
        j["segments"][1]["text"] = (
            "Bars stand still. A voice says hello [voice:vs1]. The voice says world [voice:vs2]; a hard cut at 00:04.0."
        )
        for k, (wh, warned) in enumerate(
            (("Someone talks to the camera.", True), ("Someone talks to the camera, then a voiceover ends it.", False))
        ):
            j["report"]["what_happens"] = wh
            p = os.path.join(clips.WORK, f"j_vo{k}.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(j, f)
            r = cs("build", d, "--judgment", p, "--out", os.path.join(clips.WORK, f"build vo {k}"))
            self.assertNotIn("Traceback", r.stderr)
            self.assertEqual("vs2 is voiceover and the other lines on camera" in r.stdout, warned, r.stdout)

    def test_report_wording_after_quotes_and_uncertain_people(self):
        def edit(j):
            j["lines"][0].update({"fix": {"world": "world."}, "speaker": "protagonist"})
            j["people"] = [
                {
                    "id": "protagonist",
                    "semantic": "a person",
                    "time": [0, "end"],
                    "attributes": {"role": "protagonist"},
                },
                {
                    "id": "supporting_a",
                    "semantic": "the person in every clip",
                    "time": [0, "end"],
                    "attributes": {"role": "supporting"},
                    "uncertain": ["whether every clip shows the same person"],
                },
            ]
            j["segments"][1]["text"] = (
                "Bars stand still. [image:protagonist] says, smiling [voice:vs1]. "
                "[image:supporting_a] waits; a hard cut at 00:04.0."
            )
            j["segments"][1]["cannot_judge"] = ["tone of voice and pitch"]
            j["cannot_judge"] = ["tone of voice, pitch and energy of every line"]

        r, out = self.build("wording3", edit=edit)
        ok(self, r)
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("smiling: \u201chello world.\u201d", md)
        self.assertIn(".\u201d A second person (uncertain: whether every clip shows the same person) waits", md)
        self.assertIn("- the second person: whether every clip shows the same person", md)
        self.assertIn("- tone of voice, pitch and energy of every line", md)
        self.assertNotIn("- tone of voice and pitch", md)

    def test_articles(self):
        fa = riffsheet_lib.report.fix_articles
        self.assertEqual(fa("a oatmeal sweater, a apple, A egg"), "an oatmeal sweater, an apple, An egg")
        self.assertEqual(
            fa("a one-off, a uniform, a euro, a umbrella, a LED, a 8"),
            "a one-off, a uniform, a euro, an umbrella, a LED, a 8",
        )

    def test_merge_items(self):
        m = riffsheet_lib.report.merge_items
        self.assertEqual(m(["b x", "a b x y", "b x", "z"]), ["a b x y", "z"])
        self.assertEqual(m(["same words", "words same"]), ["same words"])


if __name__ == "__main__":
    unittest.main()
