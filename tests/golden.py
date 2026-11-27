"""Golden comparison: run a fixed sequence of commands and record every output byte.

A change meant to keep behavior (a refactor, a lint fix) must leave every output file, every printed
line and every exit code exactly as they were. This script runs the tool on the clips the tests draw
(and, when RIFFSHEET_GOLDEN_REAL names a folder of earlier real runs, replays those too), then writes a
manifest: a hash of each output file, and the exit code, stdout and stderr of each command.

    python3 -B tests/golden.py WORK --write manifest.json      record (before the change)
    python3 -B tests/golden.py WORK --compare manifest.json    check (after it); exit 1 if anything differs

Run before and after from the same absolute WORK folder, with the same Python and the same ffmpeg build:
paths, the interpreter's path and the JPEG encoder all reach the outputs. The only parts normalized are
the scan's wall-clock time (index.json "scan_seconds") and the memory addresses in ffmpeg's error lines.
The clips are drawn into WORK once and reused.

A folder of real runs holds one folder per run, each with in/video.mp4, the transcript the scan used,
J.json (the judgment) and scan/index.json, whose followups are replayed in order. The real videos are
read where they are and never copied into the repository.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "scripts", "riffsheet.py")
sys.path.insert(0, ROOT)

SCAN_SECONDS = re.compile(rb'"scan_seconds": [0-9.]+')
ADDRESS = re.compile(r" @ 0x[0-9a-f]+\]")  # ffmpeg's error lines name the decoder's memory address


class Runner:
    def __init__(self, cwd):
        self.cwd = cwd
        self.log = []

    def __call__(self, *args):
        argv = [str(a) for a in args]
        r = subprocess.run([sys.executable, "-I", TOOL] + argv, capture_output=True, text=True, cwd=self.cwd)
        self.log.append(
            {
                "args": argv,
                "code": r.returncode,
                "stdout": ADDRESS.sub(" @ 0x]", r.stdout),
                "stderr": ADDRESS.sub(" @ 0x]", r.stderr),
            }
        )
        return r


def draw_clips(clip_dir):
    """The test suite's clips, drawn once into clip_dir. Returns name -> path."""
    from tests import clips as t

    names = os.path.join(clip_dir, "clips.json")
    if os.path.exists(names):
        with open(names, encoding="utf-8") as f:
            return json.load(f)
    os.makedirs(clip_dir, exist_ok=True)
    t.WORK = clip_dir
    t.make_clips()
    with open(names, "w", encoding="utf-8") as f:
        json.dump(t.CLIPS, f, indent=1, sort_keys=True)
    return dict(t.CLIPS)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return path


def states_by_on(d, name):
    with open(os.path.join(d, "look", name + ".json"), encoding="utf-8") as f:
        return {s["on"]: s["id"] for s in json.load(f)["states"]}


def drawn(run, out, clips):
    """The fixed sequence on the drawn clips: every command, the build paths, and failures."""
    from tests import clips as t

    run("--version")
    run("--help")
    # main clip: cuts, a caption on a still picture, a red block on a moving one, a tone, two words
    d = os.path.join(out, "scan main")
    run("scan", clips["main"], "--out", d, "--transcript", clips["main_transcript"])
    run("text", d, "--box", "0.05,0.75,0.95,0.88", "--name", "cap")
    run("text", d, "--box", "0.05,0.75,0.95,0.88", "--from", "2.0", "--to", "4.0")
    run("element", d, "--box", "0.05,0.10,0.45,0.32", "--at", "5.0", "--name", "red")
    run("zoom", d, "--at", "1.0", "--at", "3.0", "--at", "5.0")
    run("zoom", d, "--at", "3.0", "--box", "0.1,0.2,0.6,0.7")
    run("zoom", d, "--frame", "100", "--box", "0.0,0.0,0.5,0.5", "--name", "zf")
    run("frames", d, "--from", "2.3", "--to", "3.6", "--every", "2")
    run("frames", d, "--from", "2.3", "--to", "2.6", "--name", "moves")
    run("frames", d, "--from", "4.4", "--to", "4.7", "--box", "0.0,0.0,0.5,0.4")
    run("mouth", d, "--box", "0.3,0.3,0.7,0.5", "--words", "0-1")
    run("mouth", d, "--box", "0.3,0.3,0.7,0.5", "--line", "0", "--every-frame")
    run("color", d, "--at", "5.0", "--box", "0.12,0.17,0.32,0.24")
    run("color", d, "--at", "3.0", "--box", "0.0,0.0,0.14,0.6", "--ref", "0.7,0.0,0.85,0.6")
    run("build", d)
    ids = states_by_on(d, "cap")
    hello, world = ids[2.3], ids[3.0]
    jd = os.path.join(out, "judgments")
    os.makedirs(jd, exist_ok=True)
    for name, detail in (
        ("refused", "Bars stand on a table."),
        ("passing", "Bars stand on a {table|shot_02}."),
        ("zoomed", "Bars stand on a {table|zoom_3.00_10-20-60-70}."),
        ("moving", "Bars stand on a {table|shot_02} and {slide|moves}."),
        ("plain", "Bars stand still under soft window light; the caption sits on the bars."),
    ):
        j = write_json(os.path.join(jd, name + ".json"), t.judgment(detail, hello, world))
        run("build", d, "--judgment", j, "--out", os.path.join(out, "build " + name))
    j = t.judgment("Bars stand on a {table|shot_02}.", hello, world)
    j["graphics"][0]["description"] = 7
    run("build", d, "--judgment", write_json(os.path.join(jd, "bad.json"), j), "--out", os.path.join(out, "build bad"))
    # failures: one line on stderr each
    run("text", d, "--box", "0.5,0.5,0.4,0.4")
    run("zoom", d)
    run("mouth", d, "--from", "1", "--to", "2")
    run("build", d, "--judgment", os.path.join(jd, "missing.json"))
    run("scan", clips["text"], "--out", os.path.join(out, "scan text"))
    run("scan", clips["image"], "--out", os.path.join(out, "scan image"))
    run("scan", clips["audio_only"], "--out", os.path.join(out, "scan audio"))
    run("scan", os.path.join(out, "no such.mp4"), "--out", os.path.join(out, "scan none"))
    # fx clip: a caption leaving before a cut, a flash and a dip, a transcript with pauses
    d = os.path.join(out, "scan fx")
    run("scan", clips["fx"], "--out", d, "--transcript", clips["fx_transcript"])
    run("text", d, "--box", "0.05,0.36,0.95,0.60", "--to", "1.95", "--name", "cap")
    run("frames", d, "--from", "2.4", "--to", "3.1")
    with open(os.path.join(d, "look", "cap.json"), encoding="utf-8") as f:
        last = json.load(f)["states"][-1]["id"]
    formula = {k: "x" for k in t.riffsheet_lib.constants.FORMULA_KEYS}
    j = {
        "video_format": "single_shot",
        "language": "en",
        "lines": [{"words": "0-3", "mode": "voiceover", "speaker": "narrator"}],
        "captions": [{"id": "hook", "region": "cap", "read": [["T1-" + last, "gone soon"]], "semantic": "a hook line"}],
        "segments": [
            {"to": "end", "text": "Cells swarm, then bars, then a test pattern; the voice says a line [voice:vs1]."}
        ],
        "slots": [{"to": "end", "formula": formula}],
        "report": {"what_happens": "x", "why_it_holds": "x", "swappable": []},
    }
    run("build", d, "--judgment", write_json(os.path.join(jd, "fx.json"), j), "--out", os.path.join(out, "build fx"))
    run("build", d)
    # split: a still pane over a moving one
    d = os.path.join(out, "scan split")
    run("scan", clips["split"], "--out", d)
    run("element", d, "--box", "0.0,0.55,1.0,1.0", "--at", "2.0", "--name", "pane")
    run("text", d, "--box", "0.05,0.05,0.95,0.5", "--name", "top")
    # gap: a caption after a one-frame gap; endcard: a still card after a cut
    d = os.path.join(out, "scan gap")
    run("scan", clips["gap"], "--out", d)
    run("text", d, "--box", "0.05,0.40,0.95,0.56", "--name", "cap")
    d = os.path.join(out, "scan endcard")
    run("scan", clips["endcard"], "--out", d)
    run("element", d, "--box", "0.1,0.35,0.9,0.6", "--at", "1.5", "--name", "card")
    run("element", d, "--box", "0.1,0.35,0.9,0.8", "--at", "1.5", "--name", "card_wide")
    # frame timing, rotation, odd sizes, a long clip
    d = os.path.join(out, "scan vfr")
    run("scan", clips["vfr"], "--out", d)
    run("frames", d, "--from", "1.0", "--to", "1.3")
    for name in ("rotated", "odd", "long"):
        run("scan", clips[name], "--out", os.path.join(out, "scan " + name))


def replay(run, out, real):
    """Each real run: scan, the recorded followups in order, the sheet, the build with its judgment."""
    for name in sorted(os.listdir(real)):
        src = os.path.join(real, name)
        ix_path = os.path.join(src, "scan", "index.json")
        if not os.path.isfile(ix_path):
            continue
        with open(ix_path, encoding="utf-8") as f:
            ix = json.load(f)
        d = os.path.join(out, "real " + name)
        args = ["scan", os.path.join(src, "in", "video.mp4"), "--out", d]
        if ix.get("transcript"):
            args += ["--transcript", os.path.join(src, os.path.basename(ix["transcript"]))]
        run(*args)
        with open(os.path.join(d, "frames.json"), encoding="utf-8") as f:
            pts = json.load(f)["pts"]

        def box(b):
            return ",".join(repr(x) for x in b)

        for fu in ix.get("followups", []):
            c = fu["cmd"]
            if c == "text":
                tag = os.path.basename(fu["json"])[:-5]
                with open(os.path.join(src, "scan", fu["json"]), encoding="utf-8") as f:
                    rec = json.load(f)
                run(
                    "text",
                    d,
                    "--box",
                    box(rec["box"]),
                    "--from",
                    repr(rec["window"][0]),
                    "--to",
                    repr(rec["window"][1]),
                    "--name",
                    tag,
                )
            elif c == "element":
                run(
                    "element",
                    d,
                    "--box",
                    box(fu["box"]),
                    "--at",
                    repr(pts[fu["frames"][0]]),
                    "--name",
                    os.path.basename(fu["json"])[:-5],
                )
            elif c == "zoom":
                args = ["zoom", d]
                for fr in fu["frames"]:
                    args += ["--frame", fr]
                if fu.get("box"):
                    args += ["--box", box(fu["box"])]
                run(*args)
            elif c in ("frames", "mouth"):
                args = [c, d, "--from", repr(fu["window"][0]), "--to", repr(fu["window"][1])]
                if c == "frames":  # --every is not recorded: it is what turns the window's frames into the cells shown
                    n = sum(1 for t in pts if fu["window"][0] - 1e-6 <= t <= fu["window"][1] + 1e-6)
                    every = max(1, round(n / max(1, sum(im["cells"] for im in fu["images"]))))
                    if every > 1:
                        args += ["--every", every]
                if fu.get("box"):
                    args += ["--box", box(fu["box"])]
                run(*args)
            elif c == "color":
                args = ["color", d, "--at", repr(pts[fu["frames"][0]]), "--box", box(fu["box"])]
                if fu.get("ref"):
                    args += ["--ref", fu["ref"]]
                run(*args)
        run("build", d)
        run("build", d, "--judgment", os.path.join(src, "J.json"), "--out", os.path.join(out, "real " + name + " out"))


def digest(path):
    with open(path, "rb") as f:
        data = f.read()
    if os.path.basename(path) == "index.json":
        data = SCAN_SECONDS.sub(b'"scan_seconds": 0', data)
    return hashlib.sha256(data).hexdigest()


def manifest(work):
    out = os.path.join(work, "run")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    run = Runner(cwd=work)
    clips = draw_clips(os.path.join(work, "clips l'été"))
    drawn(run, out, clips)
    real = os.environ.get("RIFFSHEET_GOLDEN_REAL")
    if real:
        replay(run, out, os.path.abspath(real))
    files = {}
    for root, dirs, names in os.walk(out):
        dirs.sort()
        for n in sorted(names):
            p = os.path.join(root, n)
            files[os.path.relpath(p, out)] = digest(p)
    return {
        "python": sys.version.split()[0],
        "real": bool(real),
        "commands": run.log,
        "files": files,
        "clips": {k: digest(v) for k, v in sorted(clips.items())},
    }


def differences(old, new):
    diff = []
    for k in ("python", "real", "clips"):
        if old.get(k) != new.get(k):
            diff.append(f"{k}: {old.get(k)} -> {new.get(k)}")
    a, b = old["commands"], new["commands"]
    if len(a) != len(b):
        diff.append(f"{len(a)} commands before, {len(b)} now")
    for x, y in zip(a, b):
        for k in ("args", "code", "stdout", "stderr"):
            if x[k] != y[k]:
                diff.append(
                    f"command {' '.join(x['args'])}: {k} differs\n  before: {x[k]!r:.600}\n  now:    {y[k]!r:.600}"
                )
    for p in sorted(set(old["files"]) | set(new["files"])):
        if old["files"].get(p) != new["files"].get(p):
            diff.append(f"file {p}: {old['files'].get(p, 'missing')} -> {new['files'].get(p, 'missing')}")
    return diff


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", help="absolute folder for clips and outputs; use the same one before and after")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", help="write the manifest here")
    g.add_argument("--compare", help="compare with this manifest")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    m = manifest(work)
    print(f"{len(m['commands'])} commands, {len(m['files'])} files")
    if a.write:
        with open(a.write, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1, sort_keys=True)
        return 0
    with open(a.compare, encoding="utf-8") as f:
        old = json.load(f)
    diff = differences(old, m)
    for d in diff:
        print(d)
    print("identical" if not diff else f"{len(diff)} differences")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
