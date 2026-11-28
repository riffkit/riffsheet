"""The hearing check, `listen`, and what `build` does with statements of what the sound is."""

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import unittest
import wave

from tests import clips
from tests.clips import CLIPS, cs, ok, read, refused

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
from riffsheet_lib import capabilities, hearing  # noqa: E402


def setUpModule():
    clips.setUpModule()


def fake_voice(text, out_wav, tmp_wav):
    """Stands in for the speech synthesizer: a tone as long as the digits would take to say."""
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)
    clips.ff("-f", "lavfi", "-i", f"sine=frequency=440:duration={len(text) * 0.2}", "-ac", "1", "-ar", "16000", out_wav)
    return "a test voice"


def call(fn, d, **kw):
    """Run a command in this process: (exit status, what it printed, what it wrote on stderr)."""
    args = argparse.Namespace(dir=d, answer=None, cannot_hear=False, start=None, end=None)
    vars(args).update(kw)
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(args)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def copy_scan(name):
    """A scan folder of the main clip of its own (the hearing record is per analysis)."""
    d = os.path.join(clips.WORK, "hearing " + name)
    shutil.copytree(clips.scan("main", "--transcript", CLIPS["main_transcript"]), d)
    return d


class Check(unittest.TestCase):
    def setUp(self):
        self.saved = hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS
        hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS = fake_voice, lambda: "305918", 1000

    def tearDown(self):
        hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS = self.saved

    def test_marked_by_the_tool_and_the_digits_written_nowhere(self):
        d = copy_scan("marked")
        code, out, _ = call(hearing.cmd_hear_check, d)
        self.assertEqual(code, 0)
        self.assertIn("check_1.wav", out)
        self.assertIn("Do not work the digits out by measuring the file", out)
        # how to open it as sound, and what to answer, with no room to answer "cannot hear" untried
        self.assertIn("Open this file the way you open the pictures", out)
        self.assertIn("answer with the 6 digits you heard, in order, and nothing else", out)
        self.assertIn("Answer --cannot-hear only after trying", out)
        for root, _, files in os.walk(d):  # not in any file the tool wrote, as text or as bytes
            for f in files:
                with open(os.path.join(root, f), "rb") as fh:
                    self.assertNotIn(b"305918", fh.read(), f)
        self.assertEqual(hearing.hearing_state(d)["state"], "not_taken")
        # no digits: refused, nothing recorded
        self.assertEqual(call(hearing.cmd_hear_check, d, answer="I hear a tone")[0], 1)
        self.assertEqual(hearing.hearing_state(d)["state"], "not_taken")
        code, out, _ = call(hearing.cmd_hear_check, d, answer="3 0 5 9 1 7")
        self.assertIn("FAILED", out)
        self.assertEqual(hearing.hearing_state(d), {"state": "failed", "checks_answered": 1, "checks_passed": 0})
        code, _, err = call(hearing.cmd_listen, d)
        self.assertEqual(code, 1)
        self.assertIn("last hearing check failed", err)
        # an answer needs a check waiting for it
        self.assertEqual(call(hearing.cmd_hear_check, d, answer="305918")[0], 1)
        call(hearing.cmd_hear_check, d)
        code, out, _ = call(hearing.cmd_hear_check, d, answer="three: 305918")
        self.assertIn("PASSED", out)
        self.assertEqual(hearing.hearing_state(d), {"state": "passed", "checks_answered": 2, "checks_passed": 1})
        code, out, _ = call(hearing.cmd_listen, d)
        self.assertEqual(code, 0, out)
        spans = hearing.listen_clips(d)
        self.assertEqual(spans["whole"], [0.0, 6.0])
        self.assertTrue(any(k.startswith("sound_") for k in spans), spans)
        with wave.open(os.path.join(d, "listen", "whole.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (1, hearing.LISTEN_RATE))
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 6.0, delta=0.05)

    def test_any_decimal_digits_count(self):
        """An agent replying in Chinese types full-width digits; the answer is marked, not a traceback."""
        self.assertEqual(hearing.answer_digits("３０５ ٩١8"), "305918")
        d = copy_scan("full width")
        call(hearing.cmd_hear_check, d)
        code, out, err = call(hearing.cmd_hear_check, d, answer="３０５９１８")
        self.assertEqual(code, 0, err)
        self.assertIn("PASSED", out)

    def test_a_pass_counts_only_from_a_whole_record(self):
        """Only what the tool writes makes a pass: a hand-written or damaged record does not (the check is
        against an agent mistaken about itself, not against forging the record)."""
        d = copy_scan("forged")
        os.makedirs(os.path.join(d, "hearing"))
        rec = os.path.join(d, "hearing", "hearing.json")

        def write(obj):
            with open(rec, "w") as f:
                json.dump(obj, f)

        write({"checks": [{"outcome": "passed"}]})
        self.assertEqual(hearing.hearing_state(d)["state"], "not_taken")
        self.assertEqual(call(hearing.cmd_listen, d)[0], 1)
        os.remove(rec)
        call(hearing.cmd_hear_check, d)
        call(hearing.cmd_hear_check, d, answer="305918")
        self.assertEqual(hearing.hearing_state(d)["state"], "passed")
        good = json.loads(read(rec))
        for key, value in (("rounds", 1), ("salt", "x"), ("digest", None), ("file", "check_2.wav"), ("digits", 4)):
            write({"checks": [dict(good["checks"][0], **{key: value})]})
            self.assertEqual(hearing.hearing_state(d)["state"], "not_taken", key)
        write(good)
        os.rename(os.path.join(d, "hearing", "check_1.wav"), os.path.join(d, "hearing", "moved.wav"))
        self.assertEqual(hearing.hearing_state(d)["state"], "not_taken")
        # a record that is not a list of checks, or a waiting check without its hash: one line, no traceback
        for bad in ({"checks": ["passed"]}, {"checks": {}}, [1]):
            write(bad)
            refused(self, cs("listen", d), "is not one the tool wrote")
        write({"checks": [{"file": "check_1.wav"}]})
        refused(self, cs("hear-check", d, "--answer", "305918"), "is not one the tool wrote")

    def test_a_damaged_listen_record_is_one_line(self):
        d = copy_scan("damaged listen")
        os.makedirs(os.path.join(d, "listen"))
        for bad in ({"clips": [{"name": ["whole"], "span": [0, 6]}]}, {"clips": [{"name": "whole", "span": 6}]}):
            with open(os.path.join(d, "listen", "listen.json"), "w") as f:
                json.dump(bad, f)
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                hearing.listen_clips(d)

    def test_a_new_scan_forgets_the_pass_and_the_clips(self):
        """A pass and clips left in a folder belong to the video they were made for: scanning another video
        into the folder removes them (the reviewer's case: a 12 s video's clip, then an 8 s video)."""
        d = copy_scan("rescanned")
        call(hearing.cmd_hear_check, d)
        call(hearing.cmd_hear_check, d, answer="305918")
        self.assertEqual(call(hearing.cmd_listen, d, start=4.0, end=6.0)[0], 0)
        other = os.path.join(clips.WORK, "other video.mp4")
        clips.ff(
            "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=3", "-f", "lavfi", "-i", "sine=f=220:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", other,
        )  # fmt: skip
        ok(self, cs("scan", other, "--out", d))
        self.assertFalse(os.path.exists(os.path.join(d, "hearing")))
        self.assertFalse(os.path.exists(os.path.join(d, "listen")))
        self.assertEqual(hearing.hearing_state(d)["state"], "not_taken")
        self.assertEqual(hearing.listen_clips(d), {})
        code, _, err = call(hearing.cmd_listen, d)
        self.assertEqual(code, 1)
        self.assertIn("no hearing check was answered", err)

    def test_cannot_hear(self):
        d = copy_scan("cannot")
        call(hearing.cmd_hear_check, d)
        code, out, _ = call(hearing.cmd_hear_check, d, cannot_hear=True)
        self.assertIn("cannot open sound", out)
        self.assertEqual(hearing.hearing_state(d)["state"], "cannot_hear")
        self.assertEqual(call(hearing.cmd_listen, d)[0], 1)

    def test_no_audio_track_needs_no_check(self):
        d = clips.scan("split")
        code, _, err = call(hearing.cmd_hear_check, d)
        self.assertEqual(code, 1)
        self.assertIn("no audio track", err)


class Build(clips.MainClipCase):
    """Statements of what the sound is go out only after a pass, marked heard by the agent."""

    def heard_build(self, d, name, heard):
        def edit(j):
            j["heard"] = heard

        return clips.build_judgment(d, self.ids, name, edit=edit)

    def test_refused_without_a_pass_and_marked_heard_after_one(self):
        d = os.path.join(clips.WORK, "hearing build")
        shutil.copytree(self.d, d)
        tone = [{"clip": "whole", "time": [4, "end"], "about": "effect", "text": "a steady electronic tone"}]
        r, out = self.heard_build(d, "heard refused", tone)
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("NOT HEARD (1)", r.stdout)
        self.assertIn("no hearing check was answered", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(out, "riffsheet.md")))
        # the real number of rounds: `build` runs in a process of its own, and a pass counts only with them
        saved = hearing.synthesize, hearing.new_digits
        hearing.synthesize, hearing.new_digits = fake_voice, lambda: "111111"
        try:
            call(hearing.cmd_hear_check, d)
            call(hearing.cmd_hear_check, d, answer="111111")
        finally:
            hearing.synthesize, hearing.new_digits = saved
        self.assertEqual(call(hearing.cmd_listen, d)[0], 0)
        r, out = self.heard_build(d, "heard outside", [dict(tone[0], clip="sound_99")])
        self.assertIn('clip "sound_99" is not a sound file `listen` cut', r.stdout)
        r, out = self.heard_build(d, "heard", tone)
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)
        A = json.loads(read(os.path.join(out, "riffsheet.json")))
        self.assertEqual(
            A["audio"]["heard"],
            [
                {
                    "id": "h1",
                    "time_range": [4.0, 6.0],
                    "about": "effect",
                    "text": "a steady electronic tone",
                    "clip": "whole",
                    "_src": {"text": "heard"},
                }
            ],
        )
        self.assertEqual(A["_local"]["hearing"], {"state": "passed", "checks_answered": 1, "checks_passed": 1})
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("**Sound.** Heard by the agent, which passed the hearing check", md)
        self.assertIn("**Heard by the agent.** 00:04.0–00:06.0, effect: a steady electronic tone.", md)

    def passed_copy(self, name):
        d = os.path.join(clips.WORK, "hearing build " + name)
        shutil.copytree(self.d, d)
        # the real number of rounds: `build` runs in a process of its own, and a pass counts only with them
        saved = hearing.synthesize, hearing.new_digits
        hearing.synthesize, hearing.new_digits = fake_voice, lambda: "111111"
        try:
            call(hearing.cmd_hear_check, d)
            call(hearing.cmd_hear_check, d, answer="111111")
            self.assertEqual(call(hearing.cmd_listen, d)[0], 0)
        finally:
            hearing.synthesize, hearing.new_digits = saved
        return d

    def test_a_heard_time_lies_inside_this_video(self):
        """Even a listen record naming a window past the video's end (as an earlier, longer video's did)
        cannot put a heard statement outside this 6 s video."""
        d = self.passed_copy("past the end")
        p = os.path.join(d, "listen", "listen.json")
        rec = json.loads(read(p))
        rec["clips"].append({"name": "sound_09.00_11.50", "span": [9.0, 11.5]})
        with open(p, "w") as f:
            json.dump(rec, f)
        r, out = self.heard_build(
            d, "heard past the end", [{"clip": "sound_09.00_11.50", "about": "music", "text": "a song"}]
        )
        ok(self, r)
        self.assertIn("lies outside this video (0–6.0 s)", r.stdout)
        self.assertEqual(json.loads(read(os.path.join(out, "riffsheet.json")))["audio"]["heard"], [])

    def test_malformed_heard_statements_are_problems(self):
        d = self.passed_copy("malformed")
        tone = {"clip": "whole", "about": "effect", "text": "a steady electronic tone"}
        for heard, needle in (
            ([dict(tone, time=5)], "'time' is [start, end]"),
            ([dict(tone, time=[{"a": 1}, 2])], "'time' is [start, end]"),
            ([dict(tone, clip=["whole"])], 'clip ["whole"] is not a sound file'),
            ([dict(tone, about=["music"])], "'about' is one of"),
            ([dict(tone, text=["a tone"])], "give each as"),
            ("a steady tone", "heard: give a list"),
            ({"whole": "a tone"}, "heard: give a list"),
        ):
            r, out = self.heard_build(d, "heard malformed", heard)
            ok(self, r)
            self.assertIn(needle, r.stdout, heard)
            self.assertEqual(json.loads(read(os.path.join(out, "riffsheet.json")))["audio"]["heard"], [])

    def sound_claims(self, j):
        """The reviewer's judgment: what the sound is, said everywhere but under heard (the j1 case)."""
        j["report"]["what_happens"] = (
            "Three pictures in turn. An upbeat K-pop song with a heavy bass drop plays throughout, and a whoosh "
            "sound effect lands on the kick."
        )
        j["segments"][0]["text"] += " A soft piano melody plays under it."
        j["segments"][0]["uncertain"] = ["whether the tone is music cannot be judged"]
        j["own_means"] = [{"fact": "The song is an upbeat K-pop track", "used": "my own hearing"}]
        j["tool_gaps"] = ["the track is a cheerful dance song, which the tool cannot say"]
        j["cannot_judge"] = ["what the sound track is (music, effects or ambience)"]

    def test_without_a_pass_nothing_may_say_what_the_sound_is(self):
        r, out = clips.build_judgment(self.d, self.ids, "sound claims", edit=self.sound_claims)
        ok(self, r)
        for where, word in (
            ("report.what_happens", "song"),
            ("report.what_happens", "bass drop"[:4]),
            ("report.what_happens", "whoosh"),
            ("report.what_happens", "sound effect"),
            ("segments[0].text", "melody"),
            ("own_means[0].fact", "song"),
            ("tool_gaps[0]", "song"),
        ):
            self.assertIn(f"{where}: '{word}' says what the sound is, and nothing heard it", r.stdout)
        self.assertNotIn("uncertain[0]", r.stdout)  # a sentence saying the sound is not known
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("**Sound.** Not judged: no hearing check was taken for this analysis. Nothing in this", md)
        self.assertIn("as an open check", md)
        self.assertIn("## Open checks", md)
        # after a pass the agent may say it
        d = self.passed_copy("sound claims")
        r, _ = clips.build_judgment(d, self.ids, "sound claims heard", edit=self.sound_claims)
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)

    def test_not_judged_says_why(self):
        r, out = clips.build_judgment(self.d, self.ids, "no check")
        ok(self, r)
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("**Sound.** Not judged: no hearing check was taken for this analysis", md)


class RealVoice(unittest.TestCase):
    def setUp(self):
        # like a missing ffmpeg: skipped on a machine without one, a failure where everything is required
        if not hearing.synthesizer():
            why = "no speech synthesizer on PATH (say, espeak-ng, espeak)"
            if os.environ.get("RIFFSHEET_REQUIRE_FFMPEG"):
                self.fail(why + ", and RIFFSHEET_REQUIRE_FFMPEG=1 requires every program the tests use")
            self.skipTest(why)

    def test_the_synthesizer_makes_a_check(self):
        d = copy_scan("real voice")
        r = cs("hear-check", d)
        ok(self, r)
        wav = os.path.join(d, "hearing", "check_1.wav")
        with wave.open(wav) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (1, 16000))
            self.assertGreater(w.getnframes() / w.getframerate(), 2.0)
        rec = json.loads(read(os.path.join(d, "hearing", "hearing.json")))["checks"][0]
        self.assertEqual(set(rec), {"file", "made", "synthesizer", "digits", "salt", "rounds", "digest"})
        r = cs("hear-check", d, "--answer", "abc")
        refused(self, r, "no digits")


class CheckReport(unittest.TestCase):
    def test_instructions(self):
        """SKILL.md: check covers the hearing check, a system package needs a yes, the need is judged from
        what pictures can show, and the check says how to open the file and what to answer."""
        skill = read(os.path.join(clips.ROOT, "SKILL.md"))
        self.assertIn("and whether the hearing check's sound can be made here", skill)
        self.assertIn("any system package it needs", skill)
        self.assertIn("`python3-venv`", skill)
        self.assertIn("`espeak-ng`", skill)
        self.assertNotIn("cut to music", skill)  # an agent that only sees pictures cannot tell that
        self.assertIn("a voice-over cannot be seen", skill)
        self.assertIn("the way you open the pictures", skill)
        self.assertIn("Answer `rs hear-check DIR --cannot-hear` only after trying", skill)

    def test_check_says_what_needs_a_system_package(self):
        """On Debian and Ubuntu, `python3 -m venv` needs python3-venv and the hearing check needs espeak-ng:
        both are system packages, and check says so (installing one needs the person's yes)."""
        saved = capabilities.importlib.util.find_spec, capabilities.synthesizer, capabilities._in_venv
        capabilities.importlib.util.find_spec = lambda name: None
        capabilities.synthesizer, capabilities._in_venv = (lambda: None), (lambda venv: False)
        try:
            sp, hc = capabilities.speech_status(), capabilities.hearing_status()
        finally:
            capabilities.importlib.util.find_spec, capabilities.synthesizer, capabilities._in_venv = saved
        facts = " ".join(sp["facts"])
        self.assertIn("system package python3-venv", facts)
        self.assertIn("the person's yes", facts)
        facts = " ".join(hc["facts"])
        self.assertIn("espeak-ng is a system package", facts)
        self.assertIn("the person's yes", facts)

    def test_hash_times_are_the_measured_ones(self):
        """How long marking an answer and trying every answer take: only what was measured, on both
        interpreters, with the machine named (no rounded figure that a slower machine would make false)."""
        hc = capabilities.hearing_status()
        self.assertIn("marking an answer 0.38 to 0.61 s", hc["run_time"])
        tool = read(os.path.join(clips.ROOT, "references", "TOOL.md"))
        self.assertIn("0.38 s with OpenSSL 3 (Python 3.14) and 0.61 s with the LibreSSL", tool)
        self.assertIn("4 to 7 days of one such core", tool)
        self.assertNotIn("trying all million takes days", tool)

    def test_check_says_whether_the_hearing_check_can_be_made(self):
        R = json.loads(cs("check", CLIPS["split"], "--json").stdout)
        hc = next(c for c in R["capabilities"] if c["id"] == "hearing_check")
        self.assertEqual(hc["state"], "ready" if hearing.synthesizer() else "missing")
        self.assertEqual(hc["not_for_this_video"], "the video has no audio track: there is nothing to hear")
        self.assertIn("only the check", " ".join(hc["facts"]))


if __name__ == "__main__":
    unittest.main()
