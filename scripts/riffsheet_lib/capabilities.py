"""What this machine can do for an analysis, and what each optional stage did.

`check` reports ffmpeg (required) and each optional capability: ready, missing or partly there, what it
adds, what getting it costs and the commands that prepare it. `scan` records, for each optional stage,
whether it ran (and by what means), failed (and why) or did not run (and why); `build` carries that
record into riffsheet.json (`_local.stages`) and says it in riffsheet.md. Nothing here uses the network,
imports an optional package or changes the machine.

A second optional capability is one more entry in CAPABILITIES (its check, cost and commands) and one
more function in STAGE_RECORDS (what scan writes about it)."""

import glob
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from . import VERSION, util
from .constants import FFMPEG_MIN_MAJOR
from .media import probe
from .transcript import TRANSCRIBE_MODEL

# Every ffmpeg filter (and the one lavfi source, color) the tool's commands use. A build of ffmpeg without
# one of them fails on the command that needs it, so `check` names any that are missing. drawtext is the
# one most often missing: it needs ffmpeg built with freetype.
FFMPEG_FILTERS = (
    "ametadata",
    "aresample",
    "asetnsamples",
    "astats",
    "blend",
    "color",
    "crop",
    "drawbox",
    "drawgrid",
    "drawtext",
    "ebur128",
    "format",
    "interleave",
    "nullsink",
    "pad",
    "scale",
    "scdet",
    "select",
    "setpts",
    "setsar",
    "showinfo",
    "split",
    "tblend",
    "tile",
)

# Where `check` suggests installing faster-whisper: a virtual environment of its own in the user's home,
# so the system Python is never changed. `check` also looks there, so a package installed there is found
# even when the tool runs under another Python.
VENV = os.path.join("~", ".riffsheet", "venv")
# What getting speech recognition costs, measured on 2026-11-28 by installing faster-whisper 1.2.1 into a
# fresh virtual environment (Python 3.9, macOS on Apple silicon): 64.3 MB of wheels downloaded, 206.6 MB
# added on disk (214.7 MB environment minus 8.1 MB when empty). Other systems and versions differ somewhat.
SPEECH_PACKAGE_DOWNLOAD_MB = 64
SPEECH_PACKAGE_DISK_MB = 207
# The model faster-whisper fetches for the default size, and its size: model.bin 483.5 MB, tokenizer.json
# 2.2 MB, vocabulary.txt 0.5 MB, config.json 2 KB, as stored in the Hugging Face cache (the same on disk).
SPEECH_MODEL_REPO = {"small": "Systran/faster-whisper-small"}
SPEECH_MODEL_MB = {"small": 486}

SPEECH_ADDS = (
    "the spoken words, each with its start and end time, so the riffsheet quotes every line, says who says "
    "it and at what pace, and sets the sound measures against the words"
)
SPEECH_LACKS = (
    "the riffsheet quotes no spoken line and cannot say whether anyone speaks; it says that the speech was not "
    "transcribed, and why"
)


def _q(path):
    return shlex.quote(path)


def _mb(n_bytes):
    return round(n_bytes / 1e6)


# ----------------------------------------------------------------------------- ffmpeg
def ffmpeg_status():
    """ffmpeg and ffprobe: where, which version, and which of the filters the tool uses are missing."""
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    out = {"ffmpeg": ff, "ffprobe": fp, "version": None, "filters_missing": [], "needs": f"{FFMPEG_MIN_MAJOR}.0"}
    problems = []
    if not ff:
        problems.append("ffmpeg not found on PATH")
    if not fp:
        problems.append("ffprobe not found on PATH")
    if ff:
        r = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True)
        first = r.stdout.decode("utf-8", "ignore").splitlines()[:1]
        m = re.match(r"ffmpeg version (\S+)", first[0]) if first else None
        out["version"] = m.group(1) if m else None
        major = re.match(r"n?(\d+)\.", out["version"] or "")
        # a build from git reports no release number; it is taken to be recent (as the tool itself does)
        if major and int(major.group(1)) < FFMPEG_MIN_MAJOR:
            problems.append(f"ffmpeg {out['version']} is older than {FFMPEG_MIN_MAJOR}.0")
        r = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True)
        lines = r.stdout.decode("utf-8", "ignore").splitlines()
        start = next((i + 1 for i, ln in enumerate(lines) if ln.strip().startswith("---")), 0)
        have = {ln.split()[1] for ln in lines[start:] if len(ln.split()) > 1}
        out["filters_missing"] = [f for f in FFMPEG_FILTERS if f not in have]
        if out["filters_missing"]:
            problems.append("this ffmpeg lacks the filter(s) " + ", ".join(out["filters_missing"]))
    out["state"] = "missing" if problems else "ready"
    out["problems"] = problems
    return out


# ----------------------------------------------------------------------------- speech recognition
def hf_cache():
    """The Hugging Face cache folder faster-whisper reads models from (its own default rules)."""
    hub = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if hub:
        return os.path.expanduser(hub)
    home = os.environ.get("HF_HOME") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join("~", ".cache"), "huggingface"
    )
    return os.path.join(os.path.expanduser(home), "hub")


def speech_model_on_disk(model=TRANSCRIBE_MODEL):
    """(folder, size in bytes) of the model as stored in the Hugging Face cache, or None."""
    repo = SPEECH_MODEL_REPO.get(model)
    if not repo:
        return None
    pattern = os.path.join(hf_cache(), "models--" + repo.replace("/", "--"), "snapshots", "*", "model.bin")
    for mb in sorted(glob.glob(pattern)):
        if os.path.isfile(mb):  # a link into the cache's blobs: the file it points to must be there
            folder = os.path.dirname(mb)
            size = sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder))
            return folder, size
    return None


def _package_version(name):
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:  # not installed as a distribution, or metadata unreadable
        return None


def _in_venv(venv):
    """Whether faster-whisper is installed in the virtual environment at venv (looked up on disk)."""
    pkgs = glob.glob(os.path.join(venv, "lib", "python*", "site-packages", "faster_whisper", "__init__.py"))
    return bool(pkgs) and os.path.exists(os.path.join(venv, "bin", "python"))


def speech_ready_here():
    """Why speech recognition cannot run under this Python, or None when it can: the reason scan records
    when it is given no transcript."""
    if importlib.util.find_spec("faster_whisper") is None:
        return f"the faster-whisper package is not installed for the Python that ran the analysis ({sys.executable})"
    if not speech_model_on_disk():
        return f"the speech model ({TRANSCRIBE_MODEL}) is not on this machine"
    return None


def speech_status():
    """The speech recognition entry of `check`."""
    venv = os.path.expanduser(VENV)
    vpy = os.path.join(venv, "bin", "python")
    here = importlib.util.find_spec("faster_whisper") is not None
    there = not here and _in_venv(venv)
    model = speech_model_on_disk()
    tool = shlex.split(util.CMD)[-1]
    py = sys.executable if here else vpy
    run_with = f"{_q(py)} -I {_q(tool)}"
    facts, cost, prepare = [], [], []
    if here:
        v = _package_version("faster-whisper")
        facts.append(f"faster-whisper {v or '(version unknown)'} is installed for this Python ({sys.executable})")
    elif there:
        facts.append(
            f"faster-whisper is installed in {venv}, not for this Python ({sys.executable}): run every riffsheet "
            f"command with {vpy}"
        )
    else:
        facts.append(f"faster-whisper is not installed for this Python ({sys.executable}), nor in {venv}")
        cost.append(
            {
                "what": "the faster-whisper package and the packages it needs, from the Python Package Index",
                "download_mb": SPEECH_PACKAGE_DOWNLOAD_MB,
                "disk_mb": SPEECH_PACKAGE_DISK_MB,
                "network": True,
                "measured": "faster-whisper 1.2.1, Python 3.9, macOS on Apple silicon; other systems differ somewhat",
            }
        )
        prepare += [f"{_q(sys.executable)} -m venv {_q(venv)}", f"{_q(vpy)} -m pip install faster-whisper"]
    if model:
        facts.append(f"the speech model ({TRANSCRIBE_MODEL}) is on this machine: {_mb(model[1])} MB in {model[0]}")
    else:
        facts.append(f"the speech model ({TRANSCRIBE_MODEL}) is not on this machine (looked in {hf_cache()})")
        cost.append(
            {
                "what": f"the speech model ({TRANSCRIBE_MODEL}), once, into the Hugging Face cache ({hf_cache()})",
                "download_mb": SPEECH_MODEL_MB[TRANSCRIBE_MODEL],
                "disk_mb": SPEECH_MODEL_MB[TRANSCRIBE_MODEL],
                "network": True,
                "measured": "its size as stored in a Hugging Face cache",
            }
        )
        prepare.append(f"{run_with} transcribe VIDEO --out T.json --download")
    # missing: the package is not anywhere (a model alone does nothing); partly there: the package is
    # installed but the model is not here, or the package is only in the virtual environment
    state = "ready" if here and model else ("partial" if here or there else "missing")
    remove = [] if here else [f"rm -rf {_q(venv)}"]
    remove.append(
        "rm -rf " + _q(os.path.join(hf_cache(), "models--" + SPEECH_MODEL_REPO[TRANSCRIBE_MODEL].replace("/", "--")))
    )
    return {
        "id": "speech_recognition",
        "name": "speech recognition",
        "state": state,
        "facts": facts,
        "adds": SPEECH_ADDS,
        "without": SPEECH_LACKS,
        "cost": cost,
        "prepare": prepare,
        "run_with": run_with,
        "remove": remove,
    }


def speech_for_video(info):
    """Whether speech recognition matters for this video, and why."""
    if not info["has_audio"]:
        return {"needed": False, "why": "the video has no audio track"}
    return {
        "needed": True,
        "why": "the video has an audio track; whether anyone speaks in it, and what is said, is what speech "
        "recognition finds",
    }


CAPABILITIES = ((speech_status, speech_for_video),)  # (status, for_video) per optional capability


# ----------------------------------------------------------------------------- stage records (scan, build)
def speech_stage(info, transcript):
    """The speech recognition stage as scan records it. `transcript` is what load_words returned as
    metadata (None without --transcript)."""
    if transcript is not None:
        if transcript.get("stage"):  # transcribe could not make a transcript and wrote why
            return dict(transcript["stage"])
        return {
            "state": "ran",
            "by": transcript.get("model") or "a transcript given to scan (it does not say how it was made)",
        }
    if not info["has_audio"]:
        return {"state": "not_run", "why": "the video has no audio track"}
    why = speech_ready_here()
    return {
        "state": "not_run",
        "why": "no transcript was made"
        + (f", and {why}" if why else " (speech recognition was ready on this machine; `transcribe` makes one)"),
    }


STAGE_RECORDS = {"speech_recognition": speech_stage}


def stages_of(idx):
    """The stage records of a scan. A scan made before riffsheet 0.2.0 has none: they are derived from what
    it does record (a transcript, an audio track), saying so."""
    if idx.get("stages"):
        return idx["stages"]
    if idx.get("transcript_meta"):
        sp = {"state": "ran", "by": "a transcript given to scan (a scan made before riffsheet 0.2.0 does not say how)"}
    elif not idx["facts"].get("has_audio"):
        sp = {"state": "not_run", "why": "the video has no audio track"}
    else:
        sp = {"state": "not_run", "why": "no transcript was made"}
    return {"speech_recognition": sp}


STAGE_NAMES = {"speech_recognition": "Speech recognition"}
STAGE_LACKS = {
    "speech_recognition": "The speech was not transcribed: no spoken words are quoted, and whether anyone "
    "speaks is not known."
}


def stage_lines(stages, facts):
    """One sentence per optional stage that failed or did not run, for riffsheet.md and the build sheet.
    A stage that did not run because the video has nothing for it (speech, no audio track) says only that."""
    out = []
    for k, st in stages.items():
        if st["state"] == "ran":
            continue
        name = STAGE_NAMES.get(k, k)
        lack = STAGE_LACKS.get(k)
        if k == "speech_recognition" and not facts.get("has_audio"):
            lack = None
        verb = "failed" if st["state"] == "failed" else "did not run"
        out.append(f"{name} {verb}: {st['why'].rstrip('.')}." + (f" {lack}" if lack else ""))
    return out


# ----------------------------------------------------------------------------- check
def cmd_check(a):
    report = {"tool": "riffsheet", "version": VERSION, "network": "not used"}
    report["python"] = {"path": sys.executable, "version": ".".join(map(str, sys.version_info[:3]))}
    ff = ffmpeg_status()
    report["ffmpeg"] = ff
    caps = [status() for status, _ in CAPABILITIES]
    info = None
    if a.video:
        video = os.path.abspath(a.video)
        if ff["state"] != "ready" and not (ff["ffmpeg"] and ff["ffprobe"]):
            report["video"] = {"path": video, "readable": False, "why": "ffprobe is needed to read it"}
        else:
            info = probe(video)  # an unreadable file stops here, as every command does
            report["video"] = {
                "path": video,
                "duration_s": info["duration_s"],
                "width": info["width"],
                "height": info["height"],
                "has_audio": info["has_audio"],
            }
            for c, (_, for_video) in zip(caps, CAPABILITIES):
                c["for_this_video"] = for_video(info)
    report["capabilities"] = caps
    report["verdict"] = verdict(ff, caps, info)
    if a.json:
        print(json.dumps(report, indent=1, ensure_ascii=False))
        return
    print(check_text(report))


def verdict(ff, caps, info):
    if ff["state"] != "ready":
        return (
            "riffsheet cannot run here: "
            + "; ".join(ff["problems"])
            + f" (it needs ffmpeg {FFMPEG_MIN_MAJOR}.0 or newer)"
        )
    gaps = [c for c in caps if c["state"] != "ready"]
    if info is None:
        if not gaps:
            return "ready: every optional capability is ready"
        return (
            "runs here; not ready: "
            + ", ".join(c["name"] for c in gaps)
            + " (run check VIDEO to see whether it matters for a video)"
        )
    matter = [c for c in gaps if c["for_this_video"]["needed"]]
    if not matter:
        return "ready for this video" + (
            " (" + ", ".join(c["name"] + " is not ready but not needed" for c in gaps) + ")" if gaps else ""
        )
    parts = []
    for c in matter:
        if c["cost"]:
            parts.append(f"{c['name']} is not ready and matters for this video")
        else:
            parts.append(f"{c['name']} is ready under another Python: run every command with {c['run_with']}")
    asks = [c for c in matter if c["cost"]]
    tail = (
        ". Ask the person before preparing it (it downloads over the network); without it, "
        + "; ".join(c["without"] for c in asks)
        if asks
        else ""
    )
    return "; ".join(parts) + tail


def check_text(r):
    L = [f"riffsheet {r['version']} check (no network used)"]
    L.append(f"python   {r['python']['path']} ({r['python']['version']})")
    ff = r["ffmpeg"]
    if ff["state"] == "ready":
        L.append(
            f"ffmpeg   ready: ffmpeg {ff['version']} at {ff['ffmpeg']}, ffprobe at {ff['ffprobe']}; all "
            f"{len(FFMPEG_FILTERS)} filters the tool uses are present ({', '.join(FFMPEG_FILTERS)})"
        )
    else:
        L.append(f"ffmpeg   MISSING (required, {FFMPEG_MIN_MAJOR}.0 or newer): " + "; ".join(ff["problems"]))
    v = r.get("video")
    if v:
        if v.get("readable") is False:
            L.append(f"video    {v['path']}: not read ({v['why']})")
        else:
            L.append(
                f"video    {v['path']}: {v['duration_s']} s, {v['width']}x{v['height']}, "
                f"audio track {'yes' if v['has_audio'] else 'no'}"
            )
    for c in r["capabilities"]:
        L.append("")
        state = {"ready": "ready", "missing": "MISSING", "partial": "PARTLY THERE"}[c["state"]]
        L.append(f"{c['name']} (optional): {state}")
        for f in c["facts"]:
            L.append(f"  - {f}")
        L.append(f"  adds: {c['adds']}")
        L.append(f"  without it: {c['without']}")
        if "for_this_video" in c:
            fv = c["for_this_video"]
            L.append(f"  for this video: {'needed' if fv['needed'] else 'not needed'} ({fv['why']})")
        if c["state"] != "ready":
            if c["cost"]:
                L.append("  what getting it costs:")
                for x in c["cost"]:
                    L.append(
                        f"    - {x['what']}: about {x['download_mb']} MB to download, {x['disk_mb']} MB on disk, "
                        f"needs the network ({x['measured']})"
                    )
            if c["prepare"]:
                L.append("  prepare it (only with the person's yes; the system Python is not changed):")
                L += [f"    {x}" for x in c["prepare"]]
            L.append(f"  then run every riffsheet command with: {c['run_with']}")
            L.append("  to remove it later: " + "; ".join(c["remove"]))
    L.append("")
    L.append("VERDICT: " + r["verdict"])
    return "\n".join(L)
