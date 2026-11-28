"""`check` and the optional stages: what this machine can do, and a riffsheet that says what did not run."""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from tests import clips
from tests.clips import CLIPS, TOOL, cs, index, judgment, ok, read, refused

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
import riffsheet_lib.capabilities as caps  # noqa: E402
from riffsheet_lib import build, report  # noqa: E402

from tests.test_build_checks import prose, state  # noqa: E402


def setUpModule():
    clips.setUpModule()


def without_faster_whisper(*args, env=None):
    """Run the tool with faster-whisper unimportable, whether or not it is installed here."""
    argv = [TOOL] + [str(a) for a in args]
    code = (
        "import runpy, sys; sys.modules['faster_whisper'] = None; "
        f"sys.argv = {argv!r}; runpy.run_path(sys.argv[0], run_name='__main__')"
    )
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env)


def empty_home():
    """An environment whose home and Hugging Face cache are empty folders: nothing is prepared."""
    home = tempfile.mkdtemp(prefix="riffsheet-home-", dir=clips.WORK)
    env = dict(os.environ, HOME=home, HF_HOME=os.path.join(home, "hf"))
    for k in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "XDG_CACHE_HOME"):
        env.pop(k, None)
    return home, env


class Check(unittest.TestCase):
    def test_nothing_prepared(self):
        home, env = empty_home()
        r = without_faster_whisper("check", CLIPS["main"], "--json", env=env)
        ok(self, r)
        R = json.loads(r.stdout)
        self.assertEqual(R["ffmpeg"]["state"], "ready")
        self.assertEqual(R["ffmpeg"]["filters_missing"], [])
        (sp,) = R["capabilities"]
        self.assertEqual((sp["id"], sp["state"]), ("speech_recognition", "missing"))
        # facts only: no verdict on whether this video needs it
        self.assertNotIn("verdict", R)
        self.assertNotIn("not_for_this_video", sp)
        # the package and the model, each with its measured size, time, the network and nothing sent
        self.assertEqual([c["download_mb"] for c in sp["cost"]], [caps.SPEECH_PACKAGE_DOWNLOAD_MB, 486])
        self.assertTrue(all(c["network"] and not c["sends_media"] and c["time"] for c in sp["cost"]))
        venv = os.path.join(home, ".riffsheet", "venv")
        vpy = shlex.quote(os.path.join(venv, "bin", "python"))
        self.assertIn("-m venv " + shlex.quote(venv), sp["prepare"][0])
        self.assertEqual(sp["prepare"][1], f"{vpy} -m pip install faster-whisper")
        self.assertTrue(sp["prepare"][2].endswith("transcribe VIDEO --out T.json --download"), sp["prepare"])
        self.assertTrue(sp["prepare"][2].startswith(f"{vpy} -I "), sp["prepare"])
        # removing takes away what preparing adds: the environment and the model
        self.assertEqual(len(sp["remove"]), 2)
        self.assertIn("knows nothing about other tools", R["covers"])
        # the same as text
        r = without_faster_whisper("check", CLIPS["main"], env=env)
        ok(self, r)
        self.assertIn("speech recognition (optional; the tool's tested path", r.stdout)
        self.assertIn("): MISSING", r.stdout)
        self.assertIn(f"about {caps.SPEECH_PACKAGE_DOWNLOAD_MB} MB to download", r.stdout)
        self.assertIn("sends no audio or video anywhere", r.stdout)
        self.assertNotIn("VERDICT", r.stdout)
        self.assertNotIn("needed", r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith(R["covers"]), r.stdout[-300:])

    def test_no_audio_track_is_a_plain_exclusion(self):
        _, env = empty_home()
        R = json.loads(without_faster_whisper("check", CLIPS["split"], "--json", env=env).stdout)
        self.assertEqual(
            R["capabilities"][0]["not_for_this_video"], "the video has no audio track: there is nothing to transcribe"
        )

    def test_removing_lists_only_what_preparing_adds(self):
        home, env = empty_home()
        snap = os.path.join(home, "hf", "hub", "models--Systran--faster-whisper-small", "snapshots", "abc")
        os.makedirs(snap)
        with open(os.path.join(snap, "model.bin"), "wb") as f:
            f.write(b"0" * 1000)
        sp = json.loads(without_faster_whisper("check", "--json", env=env).stdout)["capabilities"][0]
        # the model is here: preparing downloads only the package, and removing deletes only its environment
        self.assertEqual([c["download_mb"] for c in sp["cost"]], [caps.SPEECH_PACKAGE_DOWNLOAD_MB])
        self.assertEqual(sp["remove"], ["rm -rf " + shlex.quote(os.path.join(home, ".riffsheet", "venv"))])

    def test_found_in_the_suggested_environment_and_model_in_cache(self):
        home, env = empty_home()
        venv = os.path.join(home, ".riffsheet", "venv")
        pkg = os.path.join(venv, "lib", "python3.9", "site-packages", "faster_whisper")
        os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").close()
        os.makedirs(os.path.join(venv, "bin"))
        open(os.path.join(venv, "bin", "python"), "w").close()
        snap = os.path.join(home, "hf", "hub", "models--Systran--faster-whisper-small", "snapshots", "abc")
        os.makedirs(snap)
        with open(os.path.join(snap, "model.bin"), "wb") as f:
            f.write(b"0" * 1000)
        R = json.loads(without_faster_whisper("check", "--json", env=env).stdout)
        sp = R["capabilities"][0]
        self.assertEqual((sp["state"], sp["cost"], sp["prepare"], sp["remove"]), ("partial", [], [], []))
        self.assertTrue(sp["run_with"].startswith(shlex.quote(os.path.join(venv, "bin", "python")) + " -I "))
        self.assertIn("installed in " + venv, sp["facts"][0])

    def test_every_listed_filter_is_used(self):
        src = "".join(read(p) for p in clips.SOURCES if not p.endswith("capabilities.py"))
        for f in caps.FFMPEG_FILTERS:
            self.assertRegex(src, r"[\"',;\]\[ ]%s[=,;\[\"]" % re.escape(f), f)


class Stages(unittest.TestCase):
    """Every optional stage ends ran, failed or not_run, and the riffsheet says so."""

    def test_transcribe_leaves_a_record_of_why(self):
        t = os.path.join(clips.WORK, "t missing.json")
        refused(self, without_faster_whisper("transcribe", CLIPS["main"], "--out", t), "faster-whisper")
        rec = json.loads(read(t))
        self.assertEqual(rec["segments"], [])
        self.assertEqual(rec["stage"]["state"], "not_run")
        self.assertIn("faster-whisper package is not installed", rec["stage"]["why"])
        d = os.path.join(clips.WORK, "scan with record")
        r = cs("scan", CLIPS["main"], "--out", d, "--transcript", t)
        ok(self, r)
        ix = index(d)
        self.assertEqual(ix["stages"]["speech_recognition"], rec["stage"])
        self.assertIsNone(ix["transcript_meta"])
        self.assertIn("NOT IN THIS SCAN: Speech recognition did not run: the faster-whisper", r.stdout)
        refused(self, cs("transcribe", CLIPS["split"], "--out", t), "no audio stream")
        self.assertEqual(json.loads(read(t))["stage"], {"state": "not_run", "why": "the video has no audio track"})

    def test_a_record_with_words_is_refused(self):
        t = os.path.join(clips.WORK, "t bad record.json")
        with open(t, "w", encoding="utf-8") as f:
            json.dump({"segments": [{"start": 0, "end": 1, "text": "hi"}], "stage": {"state": "failed", "why": "x"}}, f)
        refused(self, cs("scan", CLIPS["main"], "--out", os.path.join(clips.WORK, "y"), "--transcript", t), "holds no")

    def test_ran_with_a_transcript(self):
        d = clips.scan("main", "--transcript", CLIPS["main_transcript"])
        sp = index(d)["stages"]["speech_recognition"]
        self.assertEqual(
            sp, {"state": "ran", "by": "a transcript given to scan that does not say what made it", "tested": False}
        )
        d = os.path.join(clips.WORK, "scan main transcript by")
        r = cs(
            "scan",
            CLIPS["main"],
            "--out",
            d,
            "--transcript",
            CLIPS["main_transcript"],
            "--transcript-by",
            "whisper.cpp large-v3",
        )
        ok(self, r)
        self.assertEqual(
            index(d)["stages"]["speech_recognition"], {"state": "ran", "by": "whisper.cpp large-v3", "tested": False}
        )
        self.assertIn(
            "TRANSCRIPT: The spoken words were transcribed by whisper.cpp large-v3, not by the tool's tested path",
            r.stdout,
        )
        refused(self, cs("scan", CLIPS["main"], "--out", d, "--transcript-by", "x"), "--transcript-by")

    def test_tested_path_is_transcribe_with_the_default_model(self):
        info = {"has_audio": True}
        for model, by, tested in (
            ("faster-whisper small (int8, cpu)", None, True),
            ("faster-whisper medium (int8, cpu)", None, False),
            ("faster-whisper small (int8, cpu)", "the person's own transcript", False),
            ("whisper-1", None, False),
        ):
            st = caps.speech_stage(info, {"model": model}, by)
            self.assertEqual((st["state"], st["tested"]), ("ran", tested), (model, by))
        self.assertEqual(
            caps.speech_stage(info, {"model": "whisper-1"})["by"], "whisper-1 (as the transcript names it)"
        )
        # a record written while 0.2.0 was in development, without `tested`, gets it from `by`
        old = {"stages": {"speech_recognition": {"state": "ran", "by": "faster-whisper small (int8, cpu)"}}}
        self.assertTrue(caps.stages_of(old)["speech_recognition"]["tested"])

    def test_a_recognizer_that_stops_while_running_failed(self):
        """Present but failing at run time is `failed`, told apart from not installed (`not_run`)."""
        t = os.path.join(clips.WORK, "t broken.json")
        model_dir = tempfile.mkdtemp(prefix="riffsheet-model-", dir=clips.WORK)
        argv = [TOOL, "transcribe", CLIPS["main"], "--out", t]
        code = (
            "import runpy, sys, types\n"
            "np = types.ModuleType('numpy'); np.int16 = np.float32 = None\n"
            "class A:\n"
            "    def __init__(s, b): s.n = len(b) // 2\n"
            "    def astype(s, t): return s\n"
            "    def __truediv__(s, x): return s\n"
            "    def __len__(s): return s.n\n"
            "np.frombuffer = lambda b, t: A(b)\n"
            "fw = types.ModuleType('faster_whisper')\n"
            f"fw.download_model = lambda *a, **k: {model_dir!r}\n"
            "def broken(*a, **k): raise RuntimeError('unable to open file model.bin')\n"
            "fw.WhisperModel = broken\n"
            "sys.modules.update(numpy=np, faster_whisper=fw)\n"
            f"sys.argv = {argv!r}; runpy.run_path(sys.argv[0], run_name='__main__')\n"
        )
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        refused(self, r, "faster-whisper stopped with RuntimeError")
        st = json.loads(read(t))["stage"]
        self.assertEqual(st["state"], "failed")
        (line,) = caps.stage_lines({"speech_recognition": st}, {"has_audio": True})
        self.assertTrue(line.startswith("Speech recognition was there but failed while running: faster-whisper"), line)

    def test_no_audio_track(self):
        sp = index(clips.scan("split"))["stages"]["speech_recognition"]
        self.assertEqual(sp, {"state": "not_run", "why": "the video has no audio track"})

    def test_riffsheet_without_speech_recognition(self):
        d = os.path.join(clips.WORK, "scan main untranscribed")
        r = cs("scan", CLIPS["main"], "--out", d)
        ok(self, r)
        self.assertIn("NOT IN THIS SCAN: Speech recognition did not run: no transcript was made", r.stdout)
        self.assertIn("loudness events (speech not transcribed", r.stdout)
        self.assertNotIn("with no word under them", r.stdout)
        ok(self, cs("text", d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap"))
        ok(self, cs("element", d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red"))
        sheet = cs("build", d)
        ok(self, sheet)
        self.assertIn("no transcript words: speech recognition did not run: no transcript was made", sheet.stdout)
        states = json.loads(read(os.path.join(d, "look", "cap.json")))["states"]
        ids = [next(s["id"] for s in states if s["on"] == t) for t in (2.3, 3.0)]

        def run(name, what_happens):
            j = judgment("Bars stand still.", *ids)
            j.pop("lines")
            j["captions"][0].pop("voice_anchor")
            j["captions"][0]["semantic"] = "a caption"
            j["segments"][1]["text"] = "Bars stand still; a hard cut at 00:04.0."
            j["report"]["what_happens"] = what_happens
            p = os.path.join(clips.WORK, name + ".json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(j, f)
            out = os.path.join(clips.WORK, "build " + name)
            return cs("build", d, "--judgment", p, "--out", out), out

        r, _ = run("untranscribed claim", "Three pictures in turn; nobody speaks.")
        self.assertIn("'nobody speaks', but the speech was not transcribed", r.stdout)
        r, out = run("untranscribed", "Three pictures in turn.")
        ok(self, r)
        self.assertIn("CHECKS: all passed", r.stdout)
        self.assertIn("speaking none (speech not transcribed)", r.stdout)
        A = json.loads(read(os.path.join(out, "riffsheet.json")))
        self.assertEqual(A["_local"]["stages"]["speech_recognition"]["state"], "not_run")
        self.assertEqual(A["metadata"]["_src"]["speaking_mode"], "cannot_judge_locally")
        md = read(os.path.join(out, "riffsheet.md")).splitlines()
        self.assertIn("· speech not transcribed", md[2])
        self.assertNotIn("no speech", "\n".join(md))
        self.assertTrue(md[4].startswith("**Not in this analysis.** Speech recognition did not run:"), md[4])
        self.assertIn("whether anyone speaks is not known", md[4])


class OtherMeans(clips.MainClipCase):
    """What the agent did by its own means, and what the tool lacked, are said in riffsheet.md."""

    def test_riffsheet_says_what_came_from_elsewhere(self):
        def edit(j):
            j["own_means"] = [{"fact": "The tone is a 440 Hz sine", "used": "a spectrum of my own", "time": [4, "end"]}]
            j["tool_gaps"] = ["no command measures pitch"]

        r, out = self.build("other means", edit=edit)
        ok(self, r)
        self.assertIn("OUTSIDE THE TESTED PATH: The spoken words were transcribed by a transcript given", r.stdout)
        A = json.loads(read(os.path.join(out, "riffsheet.json")))
        self.assertEqual(
            A["_local"]["own_means"],
            [{"fact": "The tone is a 440 Hz sine", "used": "a spectrum of my own", "time_range": [4.0, 6.0]}],
        )
        md = read(os.path.join(out, "riffsheet.md"))
        self.assertIn("**Outside the tool's tested path.** The spoken words were transcribed by", md)
        self.assertIn("## Established by the agent's own means, outside the tool", md)
        self.assertIn("- The tone is a 440 Hz sine (used: a spectrum of my own; 00:04.0–00:06.0).", md)
        self.assertIn("## What the tool lacked here (recorded by the agent)\n\n- no command measures pitch", md)
        r, _ = self.build("bad other means", edit=lambda j: j.update(own_means=[{"fact": "x"}]))
        self.assertIn("own_means[0]: give each as", r.stdout)


class Words(unittest.TestCase):
    """The wording, on hand-made state (no video)."""

    def test_no_speech_claims_only_when_speech_unknown(self):
        unknown = {"speech_recognition": {"state": "not_run", "why": "no transcript was made"}}
        for stages, audio, n in ((unknown, True, 2), (unknown, False, 0), (None, True, 0)):
            s = prose(state(J={"report": {"what_happens": "A wordless clip."}}), (0, 6, "No one speaks here."))
            s.idx["facts"]["has_audio"] = audio
            if stages:
                s.idx["stages"] = stages
            else:
                s.idx["transcript_meta"] = {"language": "en", "words": 0, "lines": []}
            build.check_no_speech_claims(s)
            self.assertEqual(len(s.problems), n, (stages, audio, s.problems))

    def test_stage_lines(self):
        self.assertEqual(caps.stage_lines({"speech_recognition": {"state": "ran", "by": "x"}}, {"has_audio": True}), [])
        (line,) = caps.stage_lines({"speech_recognition": {"state": "failed", "why": "it broke."}}, {"has_audio": True})
        self.assertTrue(
            line.startswith("Speech recognition was there but failed while running: it broke. The speech was not"), line
        )
        no_audio = {"speech_recognition": {"state": "not_run", "why": "the video has no audio track"}}
        self.assertEqual(
            caps.stage_lines(no_audio, {"has_audio": False}),
            ["Speech recognition did not run: the video has no audio track."],
        )

    def test_headline_says_not_transcribed(self):
        m = {
            "duration_seconds": 8.0,
            "video_format": "single_shot",
            "speaking_mode": "none",
            "language": "es",
            "_src": {"language": "seen", "speaking_mode": "cannot_judge_locally"},
        }
        self.assertEqual(
            report.headline(m, 4, 0),
            "8.0 s · 4 shots · one picture at a time · speech not transcribed · on-screen text in es",
        )


if __name__ == "__main__":
    unittest.main()
