"""What scan and the follow-up commands measure, on clips drawn with known times and boxes."""

import json
import os
import shutil
import subprocess
import sys
import unittest

from tests import clips
from tests.clips import CLIPS, FPS, SCANS, TOOL, H, W, cs, ff, index, jpeg_size, ok, read, scan

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
import riffsheet_lib.constants  # noqa: E402
import riffsheet_lib.media  # noqa: E402
import riffsheet_lib.picture  # noqa: E402
import riffsheet_lib.sheets  # noqa: E402


def setUpModule():
    clips.setUpModule()


class Measurements(unittest.TestCase):
    def test_hard_cut_found(self):
        ix = index(scan("main", "--transcript", CLIPS["main_transcript"]))
        cuts = [e for e in ix["events"] if e["kind"] == "cut"]
        self.assertEqual([round(e["t"], 3) for e in cuts], [2.0, 4.0])
        self.assertTrue(all(e["onset"] == "abrupt" for e in cuts))
        self.assertEqual([(s["start"], s["end"]) for s in ix["shots"]], [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)])

    def test_caption_change_on_still_picture_is_not_a_cut(self):
        ix = index(scan("main", "--transcript", CLIPS["main_transcript"]))
        inside = [e for e in ix["events"] if 2.0 < e["t"] < 4.0]
        self.assertTrue(inside, "the caption change should be reported")
        self.assertTrue(all(e["kind"] != "cut" for e in inside), inside)
        self.assertIn("band", [e["kind"] for e in inside])

    def test_caption_on_and_off_times_exact(self):
        d = scan("main", "--transcript", CLIPS["main_transcript"])
        r = cs("text", d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap")
        ok(self, r)
        with open(os.path.join(d, "look", "cap.json"), encoding="utf-8") as f:
            states = json.load(f)["states"]
        spans = [(s["on"], s["off"]) for s in states]
        self.assertIn((2.3, 3.0), spans)  # HELLO
        self.assertIn((3.0, 3.7), spans)  # WORLD
        self.assertIn("hello", [s["spoken_during"] for s in states if (s["on"], s["off"]) == (2.3, 3.0)][0])

    def test_change_in_one_pane_is_a_panel_change(self):
        ix = index(scan("split"))
        self.assertFalse(ix["facts"]["has_audio"])
        self.assertIsNone(ix["audio"])
        ev = [e for e in ix["events"] if abs(e["t"] - 1.5) < 0.04]
        self.assertEqual(len(ev), 1, ix["events"])
        self.assertEqual(ev[0]["kind"], "panel")
        x0, y0, x1, y1 = ev[0]["box"]
        self.assertGreaterEqual(y0, 0.5)  # inside the bottom pane (it starts at 0.6)
        self.assertEqual((x0, x1, y1), (0.0, 1.0, 1.0))
        self.assertEqual(len(ix["shots"]), 1)

    def test_frame_times_are_decoder_timestamps(self):
        for name in ("main", "vfr"):
            d = scan(name) if name != "main" else scan("main", "--transcript", CLIPS["main_transcript"])
            with open(os.path.join(d, "frames.json")) as f:
                pts = json.load(f)["pts"]
            r = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v",
                    "-show_entries",
                    "frame=pts_time,best_effort_timestamp_time",
                    "-of",
                    "json",
                    CLIPS[name],
                ],
                capture_output=True,
                text=True,
            )
            fr = json.loads(r.stdout)["frames"]
            truth = [float(x.get("pts_time", x.get("best_effort_timestamp_time"))) for x in fr]
            self.assertEqual(len(pts), len(truth))
            self.assertLess(max(abs(a - b) for a, b in zip(pts, truth)), 1e-6)
        ix = index(scan("vfr"))
        self.assertTrue(ix["facts"]["variable_frame_rate"])
        self.assertEqual(ix["facts"]["frames"], 66)
        # what a sheet prints under a cell is that frame's time: the frames sheet of the 12 fps part
        r = cs("frames", scan("vfr"), "--from", "1.0", "--to", "1.3")
        ok(self, r)
        self.assertIn("4 real frames 1.000–1.250", r.stdout)

    def test_element_box_and_times(self):
        d = scan("main", "--transcript", CLIPS["main_transcript"])
        r = cs("element", d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red")
        ok(self, r)
        with open(os.path.join(d, "look", "red.json"), encoding="utf-8") as f:
            m = json.load(f)["measured"]
        truth = [40 / W, 100 / H, 120 / W, 160 / H]
        for got, want, size in zip(m["box"], truth, (W, H, W, H)):
            self.assertLessEqual(abs(got - want) * size, 3.0, (m["box"], truth))
        self.assertAlmostEqual(m["on"], 4.5, delta=0.5 / FPS)
        self.assertAlmostEqual(m["off"], 5.5, delta=0.5 / FPS)

    def test_rotated_video_is_shown_upright(self):
        d = scan("rotated")
        ix = index(d)
        self.assertEqual((ix["facts"]["width"], ix["facts"]["height"]), (640, 360))
        r = cs("color", d, "--at", "0.5", "--box", "0.02,0.70,0.13,0.97")  # where the block shows
        ok(self, r)
        self.assertRegex(r.stdout, r"\n  \d+%  #\w+  red ")

    def test_odd_dimensions(self):
        d = scan("odd")
        self.assertEqual((index(d)["facts"]["width"], index(d)["facts"]["height"]), (241, 427))
        ok(self, cs("text", d, "--box", "0.1,0.1,0.9,0.3"))
        ok(self, cs("zoom", d, "--at", "0.5", "--box", "0.33,0.33,0.67,0.67"))

    def test_long_video_warns_and_runs(self):
        d = os.path.join(clips.WORK, "scan long")
        r = cs("scan", CLIPS["long"], "--out", d)
        ok(self, r)
        self.assertIn("warning: 200 s video", r.stderr)
        self.assertIn("short clips", r.stderr)
        self.assertEqual(index(d)["overview_step_s"], 3.75)

    def test_every_image_within_size_cap(self):
        d = scan("main", "--transcript", CLIPS["main_transcript"])
        for args in (
            ("zoom", d, "--at", "1", "--at", "3", "--at", "5"),
            ("frames", d, "--from", "0", "--to", "6"),
            ("mouth", d, "--box", "0.3,0.3,0.7,0.5", "--from", "2", "--to", "3.5", "--every-frame"),
            ("text", d, "--box", "0.02,0.02,0.98,0.98", "--name", "whole"),
        ):
            ok(self, cs(*args))
        n = 0
        for folder in [d] + list(SCANS.values()):
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.endswith(".jpg"):
                        w, h = jpeg_size(os.path.join(root, f))
                        n += 1
                        self.assertLessEqual(max(w, h), riffsheet_lib.constants.MAX_SIDE, f)
                        self.assertLessEqual(w * h, riffsheet_lib.constants.MAX_PIXELS, f)
        self.assertGreater(n, 10)


class CaptionsAndFrames(unittest.TestCase):
    """A caption that leaves before a cut, a layer that cannot be told from still picture, and one-frame
    flashes and dips: measured right, or withdrawn."""

    @classmethod
    def setUpClass(cls):
        cls.d = scan("fx", "--transcript", CLIPS["fx_transcript"])
        r = cs("text", cls.d, "--box", "0.05,0.36,0.95,0.60", "--to", "1.95", "--name", "cap")
        if r.returncode:
            raise RuntimeError(r.stderr)
        cls.text_out = r.stdout
        with open(os.path.join(cls.d, "look", "cap.json"), encoding="utf-8") as f:
            cls.states = json.load(f)["states"]

    def test_caption_gone_before_cut_is_a_state_with_no_layer(self):
        on = [s for s in self.states if s["on"] == 0.0][0]
        self.assertEqual(on["off"], 1.5)
        self.assertNotIn("empty", on)
        after = [s for s in self.states if s["on"] == 1.5]
        self.assertEqual(len(after), 1, self.states)
        self.assertIn("empty", after[0])
        self.assertIn("NO LAYER", self.text_out)

    def test_build_ends_a_chunk_at_the_last_state_showing_the_layer(self):
        last = self.states[-1]["id"]
        formula = {k: "x" for k in riffsheet_lib.constants.FORMULA_KEYS}
        j = {
            "video_format": "single_shot",
            "language": "en",
            "lines": [{"words": "0-3", "mode": "voiceover", "speaker": "narrator"}],
            "captions": [
                {"id": "hook", "region": "cap", "read": [["T1-" + last, "gone soon"]], "semantic": "a hook line"}
            ],
            "segments": [
                {"to": "end", "text": "Cells swarm, then bars, then a test pattern; the voice says a line [voice:vs1]."}
            ],
            "slots": [{"to": "end", "formula": formula}],
            "report": {"what_happens": "x", "why_it_holds": "x", "swappable": []},
        }
        p = os.path.join(clips.WORK, "j_fx.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(j, f)
        out = os.path.join(clips.WORK, "build fx")
        r = cs("build", self.d, "--judgment", p, "--out", out)
        ok(self, r)
        with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
            A = json.load(f)
        cap = [e for e in A["scene_entities"] if e["kind"] == "subtitle"][0]
        self.assertEqual(cap["time_range"], [0.0, 1.5])
        self.assertEqual(cap["_src"]["time_range"], "measured")
        self.assertIn("shows no drawn layer", " ".join(cap["_notes"]))
        # a layer the still cells held with reaches the box's edges: size and place withdrawn, not guessed
        self.assertNotIn("approximate_size", cap["params"])
        self.assertNotIn("position_y_ratio", cap["params"])
        # one line holding a sentence end and a comma, each followed by a pause: both warned about
        self.assertIn("WARNINGS (2)", r.stdout)
        self.assertIn("'Gone.' (word 0) ends a sentence", r.stdout)
        self.assertIn("'again,' (word 2) is followed by a 0.30 s pause", r.stdout)

    def test_layer_held_with_still_picture_is_withdrawn(self):
        ly = [s for s in self.states if s["on"] == 0.0][0]["layer"]
        self.assertFalse(ly.get("measured"), ly)
        self.assertIn("reaches", ly.get("why", "") + json.dumps(ly))

    def test_one_frame_flash_and_dip_are_measured(self):
        ix = index(self.d)
        between = {r["t"]: r for e in ix["events"] for r in e.get("between", [])}
        flash, dip = between.get(2.5), between.get(3.0)
        self.assertIsNotNone(flash, ix["events"])
        self.assertIsNotNone(dip, ix["events"])
        self.assertEqual((flash["vs_before"], flash["vs_after"]), ("lighter", "lighter"))
        self.assertEqual((dip["vs_before"], dip["vs_after"]), ("darker", "darker"))
        self.assertGreater(flash["luma"][1], 200)
        self.assertLess(dip["luma"][1], 40)
        self.assertFalse(flash["mix_of_neighbors"])
        summary = read(os.path.join(self.d, "summary.txt"))
        self.assertIn("frame 2.500 #75 is lighter than both neighbors (a flash)", summary)
        self.assertIn("frame 3.000 #90 is darker than both neighbors (a dip)", summary)


class CaptionGapAndEndCard(unittest.TestCase):
    def test_caption_after_a_one_frame_gap_is_its_own_state(self):
        d = scan("gap")
        r = cs("text", d, "--box", "0.05,0.40,0.95,0.56", "--name", "cap")
        ok(self, r)
        with open(os.path.join(d, "look", "cap.json"), encoding="utf-8") as f:
            st = json.load(f)["states"]
        spans = [(s["on"], s["off"], bool(s.get("empty"))) for s in st]
        self.assertIn((0.0, 1.5, False), spans)
        self.assertIn((1.5, 1.533, False), spans)  # the empty frame, a state of its own
        self.assertIn((1.533, 2.5, False), spans)  # the second caption: on screen, not NO LAYER
        self.assertIn((2.5, 3.0, True), spans)  # gone, the picture behind still moving

    def test_end_card_timed_but_not_boxed(self):
        d = scan("endcard")
        r = cs("element", d, "--box", "0.1,0.35,0.9,0.6", "--at", "1.5", "--name", "card")
        ok(self, r)
        self.assertIn("box not measured", r.stdout)
        self.assertIn("with its times only", r.stdout)
        self.assertNotIn("takes its box", r.stdout)
        formula = {k: "x" for k in riffsheet_lib.constants.FORMULA_KEYS}
        j = {
            "video_format": "single_shot",
            "language": "en",
            "graphics": [{"id": "end_card", "region": "card", "semantic": "an end card", "description": "a card"}],
            "segments": [
                {"to": "S2", "text": "Cells swarm; a hard cut at 00:01.0."},
                {"to": "end", "text": "A white card stays up."},
            ],
            "slots": [{"to": "end", "formula": formula}],
            "report": {"what_happens": "x", "why_it_holds": "x", "swappable": []},
        }
        for k, box in enumerate((None, [0.2, 0.4, 0.8, 0.5])):
            if box:
                j["graphics"][0].update({"box": box, "why": "drawn by eye: the card is a still picture"})
            p = os.path.join(clips.WORK, f"j_card{k}.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(j, f)
            out = os.path.join(clips.WORK, f"build card {k}")
            r = cs("build", d, "--judgment", p, "--out", out)
            ok(self, r)
            if not box:
                self.assertIn("graphic end_card: no box: region card measured its times but not its box", r.stdout)
                continue
            self.assertIn("CHECKS: all passed", r.stdout)
            with open(os.path.join(out, "riffsheet.json"), encoding="utf-8") as f:
                g = [e for e in json.load(f)["scene_entities"] if e["kind"] == "graphic"][0]
            self.assertEqual(g["time_range"], [1.0, 2.0])
            self.assertEqual(g["_src"]["time_range"], "measured")
            self.assertEqual((g["params"]["x_ratio"], g["params"]["width_ratio"]), (0.2, 0.6))


class ElementMessages(unittest.TestCase):
    """What `element` and `text` say about end cards, split seams and arrivals over several frames."""

    def test_full_frame_end_card_keeps_its_times_on_the_first_try(self):
        d = scan("endcard")
        r = cs("element", d, "--box", "0.1,0.35,0.9,0.8", "--at", "1.5", "--name", "card_wide")
        ok(self, r)
        self.assertIn("element card_wide: on 1.000", r.stdout)
        self.assertIn("with its times only", r.stdout)

    def test_box_across_a_split_seam_is_explained(self):
        # the split clip's seam (y 0.6) is too short-lived to be measured as a layout: the scan of a copy
        # is given the layout a longer clip would get, as `scan` writes it
        d = os.path.join(clips.WORK, "scan split with a layout")
        shutil.copytree(scan("split"), d)
        ix = index(d)
        seam = 0.6
        ix["panes"] = [
            {
                "axis": "top/bottom",
                "seam": seam,
                "seam_px": 384,
                "on": 0.0,
                "off": 3.0,
                "panes": [[0.0, 0.0, 1.0, seam], [0.0, seam, 1.0, 1.0]],
                "evidence": [],
                "id": "P1",
            }
        ]
        with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
            json.dump(ix, f)
        r = cs("text", d, "--box", f"0.05,{seam - 0.1:.2f},0.95,{seam + 0.1:.2f}", "--name", "across")
        ok(self, r)
        self.assertIn("This box crosses the seam between the panes", r.stdout)
        r = cs("text", d, "--box", f"0.05,0.05,0.95,{seam - 0.1:.2f}", "--name", "top_only")
        ok(self, r)
        self.assertNotIn("crosses the seam", r.stdout)

    def test_cell_inside_an_arrival_is_labeled(self):
        clip = os.path.join(clips.WORK, "fade clip.mp4")
        font = riffsheet_lib.sheets.font_path()
        fo = f"fontfile={riffsheet_lib.media.fq(font)}:" if font else ""
        ff(
            "-f",
            "lavfi",
            "-i",
            f"smptehdbars=s={W}x{H}:r={FPS}:d=3",
            "-vf",
            f"drawtext={fo}text=FADE IN:fontsize=44:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-tw)/2:y=500:alpha='if(lt(t\\,1)\\,0\\,min(1\\,(t-1)/0.2))',format=yuv420p",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            clip,
        )
        d = os.path.join(clips.WORK, "scan fade")
        ok(self, cs("scan", clip, "--out", d))
        r = cs("text", d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap")
        ok(self, r)
        self.assertIn("labeled 'mid-change a→b'", r.stdout)
        self.assertIn("not a state of its own", r.stdout)


class ParallelCommands(unittest.TestCase):
    def test_commands_run_at_once_on_one_scan_folder(self):
        """Agents run independent follow-up commands at once: none may break another, and every record
        reaches index.json."""
        d = os.path.join(clips.WORK, "scan main parallel")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(scan("main", "--transcript", CLIPS["main_transcript"]), d)
        before = len(index(d).get("followups", []))
        box = "0.05,0.75,0.95,0.88"
        cmds = [("text", d, "--box", box, "--name", f"same{k}") for k in range(3)]
        cmds += [("zoom", d, "--at", "1.0", "--name", "z1"), ("zoom", d, "--at", "5.0", "--name", "z2")]
        procs = [
            subprocess.Popen(
                [sys.executable, "-I", TOOL] + list(c), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            for c in cmds
        ]
        for c, p in zip(cmds, procs):
            _, err = p.communicate()
            self.assertEqual(p.returncode, 0, f"{c[0]} {c[-1]}: {err}")
            self.assertEqual(err, "")
        fu = index(d)["followups"][before:]
        self.assertEqual(
            sorted(f.get("json") or f["images"][0]["path"] for f in fu),
            ["look/same0.json", "look/same1.json", "look/same2.json", "look/z1.jpg", "look/z2.jpg"],
        )
        states = []
        for k in range(3):
            with open(os.path.join(d, "look", f"same{k}.json"), encoding="utf-8") as f:
                states.append(json.load(f)["states"])
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[0], states[2])
        self.assertEqual([f for f in os.listdir(d) if f.startswith(".tmp") or f.endswith((".lock", ".tmp"))], [])


class SoundBlock(unittest.TestCase):
    """The main clip's sound: a steady tone under two words, cut off at the clip's end."""

    def test_levels_events_and_what_lies_under_the_voice(self):
        a = index(scan("main", "--transcript", CLIPS["main_transcript"]))["audio"]
        self.assertEqual(a["silences"], [])  # the tone never stops
        self.assertEqual(len(a["rms_db_per_0_5s"]), 13)  # 6 s, the last 100 ms block at 6.0 s
        self.assertEqual(a["energy_segments"][0]["level"], "normal")  # the tone, from the first block
        self.assertEqual(a["under_voice"]["verdict"], "something_continues")  # the tone fills the pauses
        f = a["facts"]
        self.assertEqual(sorted(f), ["deepest_drops", "max", "min", "quietest", "sound_without_words"])
        self.assertTrue(f["sound_without_words"])  # the tone with no word under it
        summary = read(os.path.join(scan("main", "--transcript", CLIPS["main_transcript"]), "summary.txt"))
        self.assertIn("SOMETHING CONTINUES", summary)


class SoundAtCuts(unittest.TestCase):
    """Cuts against tone bursts placed by construction (tests/clips.py, beats and train)."""

    def changes(self, name):
        sc = index(scan(name))["sound_at_cuts"]
        return sc, [(c["span"][0], [x["type"] for x in c["on"]], c["nearest"]) for c in sc["changes"]]

    def test_burst_on_a_cut_off_a_cut_and_none(self):
        sc, ch = self.changes("beats")
        self.assertEqual([c[0] for c in ch], [1.0, 2.0, 4.5])
        self.assertTrue(ch[0][1])  # the burst at 1.0 starts on the cut
        on = sc["changes"][0]["on"][0]
        self.assertLessEqual(abs(on["t"] - 1.0), 0.02)
        self.assertEqual(ch[1][1], [])  # the burst half a second after the cut is not on it ...
        self.assertAlmostEqual(ch[1][2]["t"], 2.5, delta=0.02)  # ... and is named as the nearest, +0.5 s
        self.assertAlmostEqual(ch[1][2]["dt"], 0.5, delta=0.02)
        self.assertEqual(ch[2][1], [])  # nothing within 1 s of the cut at 4.5 lands on it
        self.assertEqual(sc["tolerance_s"], round(1 / 30 + 0.01, 3))
        self.assertEqual(sc["rises"], 3)  # the burst at 3.3 has no cut: counted for the baseline only
        summary = read(os.path.join(scan("beats"), "summary.txt"))
        self.assertIn("SOUND AT THE CUTS", summary)
        self.assertIn("1 of 3 cuts land on a loudness peak or rise", summary)

    def test_steady_train(self):
        sc, ch = self.changes("train")
        self.assertEqual([c[0] for c in ch], [1.0, 2.0, 2.8])
        self.assertEqual([bool(c[1]) for c in ch], [True, True, False])
        self.assertEqual(sc["rises"], 7)
        # seven onsets, each reaching 2 x 0.043 s, over 4 s: 3 cuts would land on one about 0.45 times
        self.assertAlmostEqual(sc["by_chance"], 3 * 7 * 2 * sc["tolerance_s"] / 4.0, delta=0.02)
        self.assertIn("2 of 3 cuts", read(os.path.join(scan("train"), "summary.txt")))

    def test_cuts_with_no_sound_events(self):
        sc = index(scan("main", "--transcript", CLIPS["main_transcript"]))["sound_at_cuts"]
        self.assertEqual([c["on"] for c in sc["changes"]], [[], []])  # a steady tone: nothing on the cuts
        self.assertIsNone(index(scan("split"))["sound_at_cuts"])  # no audio stream


class ScanOffersLayersAndJumps(unittest.TestCase):
    """What scan finds without being pointed at: text-like regions, a fixed layer over a moving picture
    (offered as a measured element too), and a small area that changes in one frame (a possible jump cut)."""

    @classmethod
    def setUpClass(cls):
        work = clips.WORK
        cls.fixed = os.path.join(work, "fixed card.mp4")
        # 3 s of noise (every pixel changes every frame) under a white card x 40-160, y 60-120
        ff(
            "-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}:r={FPS}:d=3",
            "-vf", "noise=alls=90:allf=t,drawbox=x=40:y=60:w=120:h=60:color=white:t=fill,"
            "drawbox=x=60:y=75:w=80:h=30:color=red:t=fill,format=yuv420p",
            "-c:v", "libx264", "-crf", "18", cls.fixed,
        )  # fmt: skip
        cls.jump = os.path.join(work, "jump.mp4")
        # 3 s of still bars; a small white square at x 200-240, y 300-340 from frame 45 (1.5 s)
        ff(
            "-f", "lavfi", "-i", f"smptehdbars=s={W}x{H}:r={FPS}:d=3",
            "-vf", "drawbox=x=200:y=300:w=40:h=40:color=white:t=fill:enable='between(n,45,89)',format=yuv420p",
            "-c:v", "libx264", "-crf", "18", cls.jump,
        )  # fmt: skip

    def test_text_region_suggested_for_a_changing_caption(self):
        d = scan("main", "--transcript", CLIPS["main_transcript"])
        regions = index(d)["text_regions"]
        self.assertEqual(len(regions), 1, regions)
        y0, y1 = regions[0]["box"][1], regions[0]["box"][3]
        self.assertTrue(y0 <= 500 / H and 544 / H <= y1, regions[0])  # holds the caption's rows
        self.assertIn("TEXT-LIKE REGIONS", read(os.path.join(d, "summary.txt")))

    def test_fixed_layer_and_element_over_a_moving_picture(self):
        d = os.path.join(clips.WORK, "scan fixed card")
        ok(self, cs("scan", self.fixed, "--out", d))
        ix = index(d)
        layers = ix["fixed_layers"]["layers"]
        self.assertEqual(len(layers), 1, layers)
        b = layers[0]["box"]
        self.assertTrue(b[0] <= 40 / W and b[1] <= 60 / H and b[2] >= 160 / W and b[3] >= 120 / H, b)
        self.assertEqual(len(ix["elements"]), 1, ix["elements"])
        el = ix["elements"][0]
        self.assertEqual(el["box"], [round(40 / W, 4), round(60 / H, 4), round(160 / W, 4), round(120 / H, 4)])
        self.assertEqual((el["on"], el["off"]), (0.0, 3.0))
        self.assertTrue(os.path.exists(os.path.join(d, "look", el["id"] + ".json")))

    def test_one_frame_change_in_a_still_picture_is_a_possible_jump_cut(self):
        d = os.path.join(clips.WORK, "scan jump")
        r = cs("scan", self.jump, "--out", d)
        ok(self, r)
        ix = index(d)
        jumps = [e for e in ix["events"] if e.get("possible_jump_cut")]
        self.assertEqual([(e["kind"], e["onset"], e["t"]) for e in jumps], [("local", "abrupt", 1.5)])
        self.assertEqual([e for e in ix["events"] if e["kind"] == "cut"], [])
        self.assertIn("jumps.jpg", [im["path"] for im in ix["images"]])
        self.assertIn("POSSIBLE JUMP CUT", r.stdout)


class JumpCut(unittest.TestCase):
    """A jump inside one framing is a cut; a graphic of about the same size popping on is not."""

    def test_jump_is_a_cut_and_the_pop_is_not(self):
        d = scan("jumpcut")
        ev = index(d)["events"]
        cuts = [e for e in ev if e["kind"] == "cut"]
        self.assertEqual(len(cuts), 1, ev)
        self.assertAlmostEqual(cuts[0]["t"], 1.0, delta=0.04)
        self.assertGreaterEqual(cuts[0]["jump_cut"]["same_colors"], riffsheet_lib.picture.JUMP_SAME_COLORS)
        b = cuts[0]["box"]  # the box holds both places of the pattern (to the grid cell), not the block
        self.assertTrue(190 / H <= b[1] <= 300 / H and b[0] <= 120 / W and b[2] >= 270 / W and b[3] >= 490 / H, b)
        pop = [e for e in ev if e["kind"] != "cut"]
        self.assertEqual([(e["kind"], e["t"], e.get("possible_jump_cut")) for e in pop], [("local", 2.0, True)])
        self.assertGreaterEqual(pop[0]["changed_fraction"], riffsheet_lib.picture.JUMP_MIN_FRAC)  # large enough ...
        self.assertNotIn("jump_cut", pop[0])  # ... but its colors are new
        self.assertEqual(len(index(d)["shots"]), 2)
        self.assertIn("in by jump cut (only box", read(os.path.join(d, "summary.txt")))


class ColorAndFrames(unittest.TestCase):
    def test_color_ref_corrects_for_the_light(self):
        clip = os.path.join(clips.WORK, "warm paper.mp4")
        # warm paper (#F0D0A0) with a cool gray square: under the paper as neutral, the square reads blue
        ff(
            "-f", "lavfi", "-i", f"color=c=0xF0D0A0:s={W}x{H}:r={FPS}:d=2",
            "-vf", "drawbox=x=100:y=200:w=160:h=160:color=0x9090A0:t=fill,format=yuv420p",
            "-c:v", "libx264", "-crf", "18", clip,
        )  # fmt: skip
        d = os.path.join(clips.WORK, "scan warm paper")
        ok(self, cs("scan", clip, "--out", d))
        r = cs("color", d, "--at", "1.0", "--box", "0.3,0.33,0.7,0.53", "--ref", "0.05,0.05,0.25,0.2")
        ok(self, r)
        self.assertIn("(light corrected with --ref)", r.stdout)
        self.assertIn("with --ref as neutral", r.stdout)
        rec = index(d)["followups"][-1]
        self.assertEqual(rec["ref"], "0.05,0.05,0.25,0.2")
        self.assertEqual([c.get("name_ref") for c in rec["colors"]], ["blue"])

    def test_frames_every_keeps_every_kth_frame(self):
        d = scan("main", "--transcript", CLIPS["main_transcript"])
        r = cs("frames", d, "--from", "2.3", "--to", "3.6", "--every", "2", "--name", "every2")
        ok(self, r)
        self.assertIn("20 real frames 2.300–3.567 (every 2)", r.stdout)
        fu = index(d)["followups"][-1]
        self.assertEqual(sum(im["cells"] for im in fu["images"]), 20)


if __name__ == "__main__":
    unittest.main()
