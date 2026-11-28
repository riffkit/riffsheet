"""Ordinary failures: one line on stderr, a non-zero status, no traceback."""

import os
import shutil
import stat
import subprocess
import sys
import time
import unittest

from tests import clips
from tests.clips import CLIPS, TOOL, cs, ok, refused, scan

sys.path.insert(0, os.path.join(clips.ROOT, "scripts"))
import riffsheet_lib  # noqa: E402
import riffsheet_lib.constants  # noqa: E402


def setUpModule():
    clips.setUpModule()


class Failures(unittest.TestCase):
    def test_version(self):
        r = cs("--version")
        ok(self, r)
        self.assertEqual(
            r.stdout.strip(),
            f"riffsheet {riffsheet_lib.VERSION} (analysis format_version {riffsheet_lib.FORMAT_VERSION})",
        )
        self.assertRegex(riffsheet_lib.VERSION, r"^\d+\.\d+\.\d+$")  # a release version, kept apart from
        self.assertIsInstance(riffsheet_lib.FORMAT_VERSION, int)  # the output format's own number

    def test_plugin_manifest_carries_the_release_version(self):
        """The Claude Code plugin manifest is a second place the release version is written."""
        import json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["version"], riffsheet_lib.VERSION)
        self.assertEqual(manifest["name"], "riffsheet")

    def test_ffmpeg_missing(self):
        empty = os.path.join(clips.WORK, "empty bin")
        os.makedirs(empty, exist_ok=True)
        r = cs("scan", CLIPS["main"], "--out", os.path.join(clips.WORK, "x"), env={"PATH": empty})
        refused(self, r, "not found on PATH")

    def test_file_missing(self):
        refused(
            self,
            cs("scan", os.path.join(clips.WORK, "nope.mp4"), "--out", os.path.join(clips.WORK, "x")),
            "video not found",
        )
        self.assertFalse(os.path.exists(os.path.join(clips.WORK, "x")))

    def test_folder_given(self):
        refused(self, cs("scan", clips.WORK, "--out", os.path.join(clips.WORK, "x")), "a folder")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_unreadable(self):
        p = os.path.join(clips.WORK, "locked.mp4")
        shutil.copy(CLIPS["vfr"], p)
        os.chmod(p, 0)
        try:
            refused(self, cs("scan", p, "--out", os.path.join(clips.WORK, "x")), "permission denied")
        finally:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)

    def test_not_media(self):
        refused(self, cs("scan", CLIPS["text"], "--out", os.path.join(clips.WORK, "x")), "ffprobe cannot read")

    def test_no_video_stream(self):
        refused(
            self,
            cs("scan", CLIPS["audio_only"], "--out", os.path.join(clips.WORK, "x")),
            "no video stream",
            "audio only",
        )

    def test_still_image(self):
        refused(self, cs("scan", CLIPS["image"], "--out", os.path.join(clips.WORK, "x")), "not a video")

    def test_help_lists_every_form_of_mouth(self):
        self.assertIn("mouth  DIR --box ... (--words A-B | --line N | --from S --to E)", cs("--help").stdout)

    def test_stale_scratch_folders_are_removed(self):
        """A command killed outright leaves its scratch folder: the next command in that scan folder
        removes the ones over a day old, and leaves a fresh one (a command running beside it) alone."""
        d = os.path.join(clips.WORK, "scan main stale")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(scan("main", "--transcript", CLIPS["main_transcript"]), d)
        names = (".tmp_text-old1", ".tmp_zoom-fresh", ".tmp_keep")
        for name in names:
            os.makedirs(os.path.join(d, name))
        day_ago = time.time() - 25 * 3600
        for name in (".tmp_text-old1", ".tmp_keep"):
            os.utime(os.path.join(d, name), (day_ago, day_ago))
        ok(self, cs("zoom", d, "--at", "1.0", "--name", "z"))
        left = sorted(f for f in os.listdir(d) if f.startswith(".tmp"))
        self.assertEqual(left, [".tmp_keep", ".tmp_zoom-fresh"])

    def test_usage_error_and_refusal_have_their_own_status(self):
        r = cs("build")  # no scan folder given
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("usage:", r.stderr)
        self.assertEqual(riffsheet_lib.constants.EXIT_REFUSED, 3)
        self.assertIn("3 `build` refused", cs("--help").stdout)

    def test_bad_arguments(self):
        d = scan("vfr")
        refused(self, cs("text", d, "--box", "0.5,0.5,0.4,0.9"), "--box")
        refused(self, cs("build", os.path.join(clips.WORK, "no scan here")), "run `scan` first")
        bad = os.path.join(clips.WORK, "bad.json")
        with open(bad, "w") as f:
            f.write("{not json")
        refused(self, cs("build", d, "--judgment", bad), "not valid JSON")
        refused(
            self,
            cs("scan", CLIPS["vfr"], "--out", os.path.join(clips.WORK, "y"), "--transcript", bad),
            "not valid JSON",
        )

    def test_transcribe_without_faster_whisper(self):
        """Runs whether or not faster-whisper is installed: the tool is started with the import blocked."""
        argv = [TOOL, "transcribe", CLIPS["main"], "--out", os.path.join(clips.WORK, "t.json")]
        code = (
            "import runpy, sys; sys.modules['faster_whisper'] = None; "
            f"sys.argv = {argv!r}; runpy.run_path(sys.argv[0], run_name='__main__')"
        )
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        refused(self, r, "faster-whisper")

    def test_no_audio_for_transcribe(self):
        r = cs("transcribe", CLIPS["split"], "--out", os.path.join(clips.WORK, "t.json"))
        refused(self, r, "no audio stream")


if __name__ == "__main__":
    unittest.main()
