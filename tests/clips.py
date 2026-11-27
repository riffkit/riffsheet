"""The clips the tests draw, and helpers to run the tool on them.

Run the tests from the repository root: python3 -B -m unittest

No video files live in the repository: every clip is generated here with ffmpeg's own test sources
(lavfi), so each expected time and box is known exactly from how the clip was drawn. All clips are
30 fps unless stated, so frame n of a part starts at n/30 s into that part.

The clips sit in a folder whose name holds a space, an accented letter and an apostrophe, so every
command also proves it copes with such paths.
"""

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "scripts", "riffsheet.py")
SCHEMA = os.path.join(ROOT, "schema", "riffsheet.schema.json")
PACKAGE = os.path.join(ROOT, "scripts", "riffsheet_lib")
SOURCES = (TOOL,) + tuple(os.path.join(PACKAGE, f) for f in sorted(os.listdir(PACKAGE)) if f.endswith(".py"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import riffsheet_lib  # noqa: E402  (the package under test, for its constants and the schema checker)
import riffsheet_lib.build  # noqa: E402
import riffsheet_lib.constants  # noqa: E402
import riffsheet_lib.details  # noqa: E402
import riffsheet_lib.media  # noqa: E402
import riffsheet_lib.report  # noqa: E402
import riffsheet_lib.schema  # noqa: E402
import riffsheet_lib.sheets  # noqa: E402

PUBLIC_TEXT = tuple(
    os.path.join(ROOT, *p.split("/"))
    for p in (
        "README.md",
        "README.zh-CN.md",
        "SKILL.md",
        "EVAL.md",
        "CHANGELOG.md",
        "references/METHOD.md",
        "references/TOOL.md",
    )
)

W, H, FPS = 360, 640, 30
WORK = None  # temporary folder, made in setUpModule
CLIPS = {}  # name -> path
SCANS = {}  # name -> scan folder (made on first use)


def ff(*args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y"] + list(args), capture_output=True)
    if r.returncode:
        raise RuntimeError("ffmpeg failed: " + r.stderr.decode("utf-8", "ignore")[-800:])


def cs(*args, env=None):
    """Run the tool as a user would, with the Python running the tests."""
    return subprocess.run(
        [sys.executable, "-I", TOOL] + [str(a) for a in args], capture_output=True, text=True, env=env
    )


def ok(test, r):
    test.assertEqual(r.returncode, 0, f"exit {r.returncode}\nstdout:\n{r.stdout[-2000:]}\nstderr:\n{r.stderr[-2000:]}")
    test.assertNotIn("Traceback", r.stderr)


def refused(test, r, *needles):
    """An ordinary problem: non-zero exit, one line on stderr naming it, no traceback."""
    test.assertNotEqual(r.returncode, 0, r.stdout)
    test.assertNotIn("Traceback", r.stderr)
    lines = [ln for ln in r.stderr.strip().splitlines() if ln.strip()]
    test.assertEqual(len(lines), 1, r.stderr)
    test.assertTrue(lines[0].startswith("riffsheet: "), lines[0])
    for n in needles:
        test.assertIn(n, lines[0])


def scan(name, *extra):
    if name not in SCANS:
        d = os.path.join(WORK, "scan " + name)
        r = cs("scan", CLIPS[name], "--out", d, *extra)
        if r.returncode:
            raise RuntimeError(f"scan of {name} failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
        SCANS[name] = d
    return SCANS[name]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def index(d):
    with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
        return json.load(f)


def jpeg_size(path):
    """Width and height from a JPEG's frame header, read without any image library."""
    with open(path, "rb") as f:
        data = f.read()
    k = 2
    while k < len(data):
        if data[k] != 0xFF:
            k += 1
            continue
        marker = data[k + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            k += 2
            continue
        seg = int.from_bytes(data[k + 2 : k + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = int.from_bytes(data[k + 5 : k + 7], "big")
            w = int.from_bytes(data[k + 7 : k + 9], "big")
            return w, h
        k += 2 + seg
    raise ValueError("no frame header in " + path)


def life(w, h, seed, color, extra=""):
    """A picture that changes everywhere every frame (cells of the game of life): a moving camera."""
    return f"life=s={w}x{h}:r={FPS}:ratio=0.3:life_color={color}:death_color=#202020:mold=0:seed={seed}" + extra


def text_filter(text, first, last, y):
    font = riffsheet_lib.sheets.font_path()
    fo = f"fontfile={riffsheet_lib.media.fq(font)}:" if font else ""
    return (
        f"drawtext={fo}text={text}:fontsize=44:fontcolor=white:borderw=3:bordercolor=black:"
        f"x=(w-tw)/2:y={y}:enable='between(n,{first},{last})'"
    )


def make_clips():
    # main: 6 s, three parts of 2 s joined by hard cuts at 2.0 and 4.0, with a sine tone throughout.
    #   0-2 s  test pattern;
    #   2-4 s  still color bars; caption HELLO on part frames 9-29 (2.300-3.000 s), WORLD on 30-50
    #          (3.000-3.700 s), drawn at y 500-544: the words change on a still picture;
    #   4-6 s  moving picture with a red box x 40-120, y 100-160 on part frames 15-44 (4.500-5.500 s).
    main = os.path.join(WORK, "main clip.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={W}x{H}:r={FPS}:d=2",
        "-f",
        "lavfi",
        "-i",
        f"smptehdbars=s={W}x{H}:r={FPS}:d=2",
        "-f",
        "lavfi",
        "-i",
        life(W, H, 1, "#3050C0", ",trim=duration=2"),
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:d=6:r=16000",
        "-filter_complex",
        f"[1:v]{text_filter('HELLO', 9, 29, 500)},{text_filter('WORLD', 30, 50, 500)}[b];"
        f"[2:v]setpts=PTS-STARTPTS,drawbox=x=40:y=100:w=80:h=60:color=red:t=fill:enable='between(n,15,44)'[c];"
        f"[0:v][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-c:a",
        "aac",
        main,
    )
    CLIPS["main"] = main
    # split: a still top pane (384 px, 60%) over a moving bottom pane (256 px) whose picture is
    # replaced at 1.5 s; the top never changes. No audio stream.
    top, bot = 384, H - 384
    split = os.path.join(WORK, "split clip.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        life(W, top, 7, "#C08030", f",trim=end_frame=1,loop=loop=89:size=1:start=0,setpts=N/{FPS}/TB"),
        "-f",
        "lavfi",
        "-i",
        life(W, bot, 1, "#3050C0", ",trim=duration=1.5"),
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={W}x{bot}:r={FPS}:d=1.5",
        "-filter_complex",
        "[1:v]setpts=PTS-STARTPTS[p];[2:v]setpts=PTS-STARTPTS[q];[p][q]concat=n=2:v=1:a=0[b];"
        "[0:v][b]vstack,format=yuv420p[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        split,
    )
    CLIPS["split"] = split
    # vfr: 1 s at 30 fps, 1 s at 12 fps, 1 s at 24 fps, stored with their own frame times
    vfr = os.path.join(WORK, "vfr.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=240x426:r=30:d=1",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=240x426:r=12:d=1",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=240x426:r=24:d=1",
        "-filter_complex",
        "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[2:v]setpts=PTS-STARTPTS[c];"
        "[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-fps_mode",
        "vfr",
        "-video_track_timescale",
        "90000",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        vfr,
    )
    CLIPS["vfr"] = vfr
    # rotated: stored 360x640 with a red block in its top-left corner, flagged to display turned 90
    # degrees (as phones record): shown 640x360 with the block at the bottom-left.
    up = os.path.join(WORK, "upright.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        life(W, H, 2, "#3050C0", ",trim=duration=1,drawbox=x=0:y=0:w=120:h=100:color=red:t=fill"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        up,
    )
    rot = os.path.join(WORK, "rotated.mp4")
    ff("-display_rotation", "90", "-i", up, "-c", "copy", rot)
    CLIPS["rotated"] = rot
    # odd: odd width and height (4:4:4 keeps them odd through the encoder)
    odd = os.path.join(WORK, "odd.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s=240x426:r={FPS}:d=1",
        "-vf",
        "scale=241:427",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",
        odd,
    )
    CLIPS["odd"] = odd
    # long: 200 s, tiny and at 2 fps, so it is long without being slow to scan
    longv = os.path.join(WORK, "long.mp4")
    ff("-f", "lavfi", "-i", "testsrc2=s=64x112:r=2:d=200", "-c:v", "libx264", "-pix_fmt", "yuv420p", longv)
    CLIPS["long"] = longv
    # not videos
    wav = os.path.join(WORK, "tone.wav")
    ff("-f", "lavfi", "-i", "sine=d=1", wav)
    CLIPS["audio_only"] = wav
    png = os.path.join(WORK, "still.png")
    ff("-f", "lavfi", "-i", "testsrc2=s=64x64:d=1", "-frames:v", "1", png)
    CLIPS["image"] = png
    txt = os.path.join(WORK, "notes.mp4")
    with open(txt, "w") as f:
        f.write("not a video\n")
    CLIPS["text"] = txt
    # fx: 4.033 s, three parts joined at 2.0 and 3.0:
    #   0-2 s    cells of the game of life (most cells change every frame, dead cells hold still, as the
    #            still parts of a locked shot do) under a small caption, part frames 0-44 (0.000-1.500 s):
    #            the caption leaves at 1.500 s while the picture keeps moving, half a second before the cut;
    #   2-3 s    still color bars, frame 15 (2.500 s) all white: a one-frame flash; frame 30 (3.000 s)
    #            all black: a one-frame dip between the bars and the next picture;
    #   3.033-   test pattern.
    fx = os.path.join(WORK, "fx clip.mp4")
    font = riffsheet_lib.sheets.font_path()
    fo = f"fontfile={riffsheet_lib.media.fq(font)}:" if font else ""
    ff(
        "-f",
        "lavfi",
        "-i",
        life(W, H, 3, "#3050C0", ",trim=duration=2"),
        "-f",
        "lavfi",
        "-i",
        f"smptehdbars=s={W}x{H}:r={FPS}:d=1.04",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={W}x{H}:r={FPS}:d=1",
        "-filter_complex",
        f"[0:v]setpts=PTS-STARTPTS,drawtext={fo}text=gone soon:fontsize=26:fontcolor=white:borderw=2:"
        f"bordercolor=black:x=(w-tw)/2:y=300:enable='between(n,0,44)'[a];"
        f"[1:v]trim=end_frame=31,setpts=PTS-STARTPTS,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,15)',"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='eq(n,30)'[b];"
        f"[2:v]setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        fx,
    )
    CLIPS["fx"] = fx
    # gap: 3 s, two parts joined by a hard cut at 2.0:
    #   0-2 s   still color bars (a locked picture) under two captions:
    #   part frames 0-44 (0.000-1.500 s)   caption "one two three four";
    #   part frame 45   (1.500-1.533 s)   no caption: one empty frame between two captions;
    #   part frames 46-59 and on past the cut to 2.500 s: caption "one two three five", at the same
    #   place: most of its strokes land where the first caption's left a frame before, so the step
    #   test (pixels held before and after) cannot see it arrive; the new strokes holding tell it.
    #   2-3 s   moving test pattern; the second caption stays on to part frame 14 (2.500 s).
    gap = os.path.join(WORK, "gap clip.mp4")
    cap = (
        f"drawtext={fo}text=%s:fontsize=30:fontcolor=white:borderw=3:bordercolor=black:"
        f"x=(w-tw)/2:y=300:enable='between(n,%d,%d)'"
    )
    ff(
        "-f",
        "lavfi",
        "-i",
        f"smptehdbars=s={W}x{H}:r={FPS}:d=2",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={W}x{H}:r={FPS}:d=1",
        "-filter_complex",
        f"[0:v]setpts=PTS-STARTPTS,{cap % ('one two three four', 0, 44)},{cap % ('one two three five', 46, 59)}[a];"
        f"[1:v]setpts=PTS-STARTPTS,{cap % ('one two three five', 0, 14)}[b];"
        f"[a][b]concat=n=2:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        gap,
    )
    CLIPS["gap"] = gap
    # endcard: 2 s, a moving picture, then a hard cut at 1.0 to a still white card with dark words that
    # holds to the end: nothing behind the card changes, so `element` can time it but not box it
    endcard = os.path.join(WORK, "endcard clip.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        life(W, H, 6, "#3050C0", ",trim=duration=1"),
        "-f",
        "lavfi",
        "-i",
        f"color=c=white:s={W}x{H}:r={FPS}:d=1",
        "-filter_complex",
        f"[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS,drawtext={fo}text=THE END:fontsize=48:"
        f"fontcolor=#202020:x=(w-tw)/2:y=280[b];[a][b]concat=n=2:v=1:a=0,format=yuv420p[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        endcard,
    )
    CLIPS["endcard"] = endcard
    # beats and train: cuts and short tone bursts (0.2 s at 700 Hz over digital silence) placed by
    # construction. beats, 6 s: cuts at 1.0, 2.0 and 4.5; bursts at 1.0 (on the first cut), 2.5 (half
    # a second after the second) and 3.3 (no cut near it); nothing within 1 s of the cut at 4.5.
    # train, 4 s: a burst every 0.5 s from 0.5; cuts at 1.0 and 2.0 (on bursts) and 2.8 (0.1 s after the
    # burst from 2.5 ends, 0.2 s before the next).
    for name, parts, bursts in (
        ("beats", (1.0, 1.0, 2.5, 1.5), (1.0, 2.5, 3.3)),
        ("train", (1.0, 1.0, 0.8, 1.2), tuple(0.5 * k for k in range(1, 8))),
    ):
        path = os.path.join(WORK, name + " clip.mp4")
        a, b, c, d = parts
        on = "+".join(f"between(t,{x:g},{x + 0.2:g})" for x in bursts)
        ff(
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s={W}x{H}:r={FPS}:d={a}",
            "-f",
            "lavfi",
            "-i",
            f"smptehdbars=s={W}x{H}:r={FPS}:d={b}",
            "-f",
            "lavfi",
            "-i",
            life(W, H, 3, "#3050C0", f",trim=duration={c}"),
            "-f",
            "lavfi",
            "-i",
            f"color=c=0xC08030:s={W}x{H}:r={FPS}:d={d}",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc=exprs='0.5*sin(2*PI*700*t)*({on})':s=16000:d={a + b + c + d:g}",
            "-filter_complex",
            "[2:v]setpts=PTS-STARTPTS[c];[0:v][1:v][c][3:v]concat=n=4:v=1:a=0,format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "4:a",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-c:a",
            "aac",
            path,
        )
        CLIPS[name] = path
    # jumpcut: 3 s on a still gray-blue background. A moving test pattern 100x180 (the "person") jumps
    # from x 120, y 300 to x 170, y 340 between part frames 29 and 30: the same things, rearranged, in
    # one frame (a jump cut inside one framing). At 2.0 s a magenta block 210x150 pops on at x 90, y 40
    # and stays: about as large, but colors that were not there (a graphic, not a cut).
    jumpcut = os.path.join(WORK, "jumpcut clip.mp4")
    ff(
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x506070:s={W}x{H}:r={FPS}:d=3",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s=100x180:r={FPS}:d=3",
        "-filter_complex",
        "[0:v][1:v]overlay=x='if(lt(n,30),120,170)':y='if(lt(n,30),300,340)',"
        "drawbox=x=90:y=40:w=210:h=150:color=0xE020E0:t=fill:enable='gte(n,60)',format=yuv420p[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        jumpcut,
    )
    CLIPS["jumpcut"] = jumpcut
    # its transcript: two sentences with pauses, the second ended by the recognizer with a comma
    tr = os.path.join(WORK, "fx transcript.json")
    with open(tr, "w", encoding="utf-8") as f:
        json.dump(
            {
                "language": "en",
                "segments": [
                    {
                        "start": 0.2,
                        "end": 2.0,
                        "text": "Gone. Look again, now",
                        "words": [
                            {"start": 0.2, "end": 0.6, "word": " Gone.", "prob": 0.9},
                            {"start": 0.9, "end": 1.2, "word": " Look", "prob": 0.9},
                            {"start": 1.2, "end": 1.5, "word": " again,", "prob": 0.9},
                            {"start": 1.8, "end": 2.0, "word": " now", "prob": 0.9},
                        ],
                    }
                ],
            },
            f,
        )
    CLIPS["fx_transcript"] = tr
    # a transcript for the main clip: two words, as faster-whisper would write them
    tr = os.path.join(WORK, "main transcript.json")
    with open(tr, "w", encoding="utf-8") as f:
        json.dump(
            {
                "language": "en",
                "segments": [
                    {
                        "start": 2.3,
                        "end": 3.4,
                        "text": "hello world",
                        "words": [
                            {"start": 2.3, "end": 2.6, "word": " hello", "prob": 0.9},
                            {"start": 3.0, "end": 3.4, "word": " world", "prob": 0.9},
                        ],
                    }
                ],
            },
            f,
        )
    CLIPS["main_transcript"] = tr


def setUpModule():
    """Draw the clips once per test run (every test module calls this)."""
    global WORK
    if WORK:
        return
    # RIFFSHEET_REQUIRE_FFMPEG=1 (set it in CI) turns a missing ffmpeg into a failure: otherwise every
    # test is skipped and the run still reports OK
    skip = unittest.SkipTest if not os.environ.get("RIFFSHEET_REQUIRE_FFMPEG") else RuntimeError
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise skip("ffmpeg and ffprobe are needed to make and read the test clips")
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    for f in ("drawtext", "life", "testsrc2", "smptehdbars"):
        if not re.search(r"\s%s\s" % f, filters):
            raise skip(f"this ffmpeg lacks the {f} filter needed to draw the test clips")
    WORK = os.path.join(tempfile.mkdtemp(prefix="riffsheet-test-"), "clips l'été")
    os.makedirs(WORK)
    make_clips()
    atexit.register(shutil.rmtree, os.path.dirname(WORK), True)


def judgment(detail, hello, world):
    """A small judgment for the main clip. `detail` is the second segment's text; `hello` and `world`
    are the ids of the caption states that show those words."""
    formula = {k: "x" for k in riffsheet_lib.constants.FORMULA_KEYS}
    return {
        "video_format": "single_shot",
        "language": "en",
        "lines": [{"words": "0-1", "mode": "voiceover", "speaker": "narrator"}],
        "captions": [
            {
                "id": "caption_vs1",
                "region": "cap",
                "read": [[hello, "HELLO"], [world, "WORLD"]],
                "semantic": "the spoken words",
                "voice_anchor": "vs1",
            }
        ],
        "graphics": [{"id": "red_box", "region": "red", "semantic": "a marker", "description": "a red block"}],
        "segments": [
            {"to": "S2", "text": "A test pattern plays; a hard cut at 00:02.0."},
            {"to": "S3", "text": detail + " The voice says hello world [voice:vs1]; a hard cut at 00:04.0."},
            {"to": "end", "text": "Cells swarm while a red block shows."},
        ],
        "slots": [{"to": "end", "formula": formula}],
        "report": {"what_happens": "Three pictures in turn.", "why_it_holds": "It changes.", "swappable": []},
    }


def build_judgment(d, ids, name, detail="Bars stand still.", edit=None):
    """Write judgment(detail) for the main clip (edited by `edit`), build it, return (result, out folder)."""
    j = judgment(detail, *ids)
    if edit:
        edit(j)
    p = os.path.join(WORK, name + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(j, f)
    out = os.path.join(WORK, "build " + name)
    return cs("build", d, "--judgment", p, "--out", out), out


def caption_ids(d):
    """The ids of the main clip's caption states that show HELLO and WORLD."""
    with open(os.path.join(d, "look", "cap.json"), encoding="utf-8") as f:
        states = json.load(f)["states"]
    return [next(s["id"] for s in states if s["on"] == t) for t in (2.3, 3.0)]


class MainClipCase(unittest.TestCase):
    """Tests on the main clip's scan, with its caption read (`cap`), its red block measured (`red`), a
    frames sheet over the caption (`moves`) and a color measured on the red block."""

    @classmethod
    def setUpClass(cls):
        cls.d = scan("main", "--transcript", CLIPS["main_transcript"])
        for args in (
            ("text", cls.d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap"),
            ("element", cls.d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red"),
            ("frames", cls.d, "--from", "2.3", "--to", "2.6", "--name", "moves"),
            ("color", cls.d, "--at", "5.0", "--box", "0.13,0.17,0.31,0.24"),
        ):
            r = cs(*args)
            if r.returncode:
                raise RuntimeError(r.stderr)
        cls.ids = caption_ids(cls.d)

    def build(self, name, detail="Bars stand still.", edit=None):
        return build_judgment(self.d, self.ids, name, detail, edit)
