"""Word-timed transcripts: loading, lookups by time, script predicates, `transcribe`."""

import os
import re
import sys
import time

from .media import check_video_path, run
from .util import die, read_json, write_json


# ----------------------------------------------------------------------------- transcript
def load_words(path):
    if not path:
        return [], None
    d = read_json(path, "transcript")
    segs = d.get("segments", []) if isinstance(d, dict) else d
    if not isinstance(segs, list) or not all(isinstance(s, dict) and "start" in s and "end" in s for s in segs):
        die(
            f'transcript {path}: expected {{"segments": [{{"start": s, "end": s, "text": ..., '
            f'"words": [{{"start": s, "end": s, "word": ...}}]}}]}} (faster-whisper\'s format)'
        )
    lang = d.get("language") if isinstance(d, dict) else None
    words = []
    for si, s in enumerate(segs):
        ws = s.get("words") or []
        if not ws and "text" in s:  # segment-level transcript: one pseudo-word per segment
            ws = [{"start": s["start"], "end": s["end"], "word": s["text"]}]
        for w in ws:
            words.append(
                {
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                    "word": str(w.get("word", "")).strip(),
                    "seg": si,
                    "prob": w.get("prob", w.get("probability")),
                }
            )
    words.sort(key=lambda x: x["start"])
    lines = [
        {"i": si, "start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text", "")).strip()}
        for si, s in enumerate(segs)
    ]
    return words, {"language": lang, "lines": lines}


def words_at(words, t):
    return [w["word"] for w in words if w["start"] <= t < w["end"]]


def words_in(words, a, b):
    return [w["word"] for w in words if w["start"] < b and w["end"] > a]


def join_words(ws):
    """Words of a line as written: no space between two characters of a script written without
    spaces (Chinese, Japanese); a space everywhere else, Korean included."""
    s = ""
    for w in ws:
        if s and not (is_unspaced_script(w[:1]) and is_unspaced_script(s[-1:])):
            s += " "
        s += w
    return s


# Three tests on a character's script, each with its own purpose, so their ranges differ on purpose:
# is_wide is for drawing (label widths: everything from the CJK radicals up is drawn about a full em
# wide); is_unspaced_script is for writing words (Han and kana have no spaces between words, Hangul
# does); counts_by_character is for pace (Chinese, Japanese and Korean are counted in characters,
# about one syllable each, Korean included even though it is written with spaces).
def is_wide(ch):
    """Wide characters (for label widths)."""
    return bool(ch) and ord(ch[0]) >= 0x2E80


def is_unspaced_script(ch):
    """A character of a script written without spaces between words: Han, kana, CJK punctuation
    and full-width forms. Hangul is written with spaces."""
    if not ch:
        return False
    o = ord(ch[0])
    return (
        0x3000 <= o <= 0x30FF
        or 0x3400 <= o <= 0x9FFF
        or 0xF900 <= o <= 0xFAFF
        or 0xFF00 <= o <= 0xFFEF
        or 0x20000 <= o <= 0x3FFFF
    )


TRANSCRIBE_MODEL = "small"  # best of base / small / medium on word errors and word times (references/TOOL.md)


def _norm_word(w):
    return re.sub(r"[^\w']", "", w.lower().replace("’", "'"))


def _align(ref, hyp):
    """Word alignment (edit distance); returns [(i or None, j or None)]."""
    n, m = len(ref), len(hyp)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    i, j, out = n, m, []
    while i or j:
        if i and j and D[i][j] == D[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and D[i][j] == D[i - 1][j] + 1:
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    return out[::-1]


def cmd_transcribe(a):
    """Word-timed transcript with faster-whisper, when it is installed (the only part of riffsheet
    that needs more than the standard library and ffmpeg)."""
    video = os.path.abspath(a.video)
    check_video_path(video)
    r = run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video]
    )
    if r.returncode != 0:
        die(f"ffprobe cannot read {video}: " + r.stderr.decode("utf-8", "ignore").strip()[-300:])
    if not r.stdout.strip():
        die("no audio stream in " + video + ": nothing to transcribe (scan works without a transcript)")
    try:
        import numpy as np
        from faster_whisper import WhisperModel, download_model
    except ImportError:
        die(
            f"transcribe needs the faster-whisper package (pip install faster-whisper), which is not "
            f"importable by this Python ({sys.executable}). If it is installed in another Python (a virtual "
            f"environment), run riffsheet with that one, for this and every other command: "
            f"/path/to/venv/bin/python -I scripts/riffsheet.py transcribe ... (every command runs on any "
            f"Python 3.9 or newer). Or scan without --transcript (no spoken lines), or make the transcript "
            'elsewhere and pass it to scan --transcript. Format: JSON {"language": "en", "segments": '
            '[{"start": s, "end": s, "text": "...", "words": [{"start": s, "end": s, '
            '"word": " word", "prob": 0.97}, ...]}, ...]} (faster-whisper\'s output with '
            "word_timestamps=True; openai-whisper's 'probability' key is read too)."
        )
    # decoded here, not by faster-whisper: its own decoder depends on the PyAV version installed
    r = run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    if r.returncode != 0:
        die("audio decode failed: " + r.stderr.decode()[-300:])
    audio = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0
    if len(audio) == 0:
        die("the video has no audio")
    try:  # a model name is resolved to a local folder first: a folder of that name here would be taken
        path = (
            a.model
            if os.path.isfile(os.path.join(a.model, "model.bin"))
            else download_model(a.model, local_files_only=not a.download, cache_dir=a.model_dir)
        )
    except Exception as e:  # the hub raises its own error types (no network, no such model, no cache)
        die(
            f"model {a.model!r} is not on this machine ({type(e).__name__}). Pass --download to fetch it "
            f"(network), or --model-dir DIR if it sits in another cache."
        )
    t0 = time.time()
    m = WhisperModel(path, device="cpu", compute_type="int8")
    # whisper's own fallback (re-decode at a higher temperature when a decode looks degenerate) stays
    # on: without it sung or music-heavy audio can come back as a stock phrase instead of the words
    segs, info = m.transcribe(audio, word_timestamps=True, language=a.language, hotwords=a.hint or None)
    out = []
    for sg in segs:
        out.append(
            {
                "start": round(sg.start, 2),
                "end": round(sg.end, 2),
                "text": sg.text.strip(),
                "words": [
                    {
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "word": w.word,
                        "prob": round(w.probability, 3),
                    }
                    for w in (sg.words or [])
                ],
            }
        )
    res = {"language": info.language, "model": f"faster-whisper {a.model} (int8, cpu)", "hint": a.hint, "segments": out}
    secs = round(time.time() - t0, 1)
    write_json(a.out, res, ensure_ascii=False, indent=1)
    nw = sum(len(sg["words"]) for sg in out)
    print(
        f"transcribe: {a.out}  model {a.model}, language {info.language}, {nw} words, {secs} s"
        + (f", hint {a.hint!r}" if a.hint else "")
    )
    for sg in out:
        print(f"  {sg['start']:6.2f}-{sg['end']:6.2f}  {sg['text']}")
    if a.compare:
        old, _ = load_words(a.compare)
        new, _ = load_words(a.out)
        A = [_norm_word(w["word"]) for w in old]
        B = [_norm_word(w["word"]) for w in new]
        diffs = []
        for i, j in _align(A, B):
            if i is not None and j is not None and A[i] == B[j]:
                continue
            t = new[j]["start"] if j is not None else old[i]["start"]
            diffs.append(
                f"{t:.2f}  {old[i]['word'] if i is not None else '-'} -> {new[j]['word'] if j is not None else '-'}"
            )
        print(
            f"  words that differ from {a.compare} ({len(diffs)}):" + ("".join("\n    " + x for x in diffs) or " none")
        )


def counts_by_character(ch):
    """A character counted one by one for pace: Han, kana and Hangul syllables."""
    o = ord(ch)
    return 0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF
