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
from riffsheet_lib import hearing  # noqa: E402


def setUpModule():
    clips.setUpModule()


def fake_voice(text, out_wav, tmp_wav):
    """Stands in for the speech synthesizer: a tone as long as the digits would take to say."""
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
        saved = hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS
        hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS = fake_voice, lambda: "111111", 1000
        try:
            call(hearing.cmd_hear_check, d)
            call(hearing.cmd_hear_check, d, answer="111111")
        finally:
            hearing.synthesize, hearing.new_digits, hearing.HEAR_ROUNDS = saved
        self.assertEqual(call(hearing.cmd_listen, d)[0], 0)
        r, out = self.heard_build(d, "heard outside", [dict(tone[0], clip="sound_99")])
        self.assertIn("clip 'sound_99' is not a sound file `listen` cut", r.stdout)
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

    def test_not_judged_says_why(self):
        r, out = clips.build_judgment(self.d, self.ids, "no check")
        ok(self, r)
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("**Sound.** Not judged: no hearing check was taken for this analysis", md)


@unittest.skipUnless(hearing.synthesizer(), "no speech synthesizer on PATH (say, espeak-ng, espeak)")
class RealVoice(unittest.TestCase):
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
    def test_check_says_whether_the_hearing_check_can_be_made(self):
        R = json.loads(cs("check", CLIPS["split"], "--json").stdout)
        hc = next(c for c in R["capabilities"] if c["id"] == "hearing_check")
        self.assertEqual(hc["state"], "ready" if hearing.synthesizer() else "missing")
        self.assertEqual(hc["not_for_this_video"], "the video has no audio track: there is nothing to hear")
        self.assertIn("only the check", " ".join(hc["facts"]))


if __name__ == "__main__":
    unittest.main()
