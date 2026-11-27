---
name: riffsheet
description: "Analyze a short video shot by shot on this machine and write a riffsheet: every cut, the camera, the people, objects and place, the on-screen text, the spoken lines with their timing, and why the video holds a viewer, beat by beat, with what to keep when making your own version. Use when the user gives a short video file (a TikTok, Reel, Short, ad or clip up to about a minute) and asks to break it down, analyze it, explain why it works or went viral, describe it shot by shot, write a video breakdown, list its cuts or captions, or plan a remake of it. Typical requests: 'break down this video', 'analyze this TikTok', 'why does this ad work', 'go through it shot by shot', 'what makes this go viral', 'I want to make my own version of this'."
---

# riffsheet

You cannot watch a video; you can read stills and text. This skill gives you a local tool that measures the video (cuts, stillness, captions, graphics, loudness, word timing) and lays out exactly the pictures you need, and a procedure for reading them. You write judgment; the tool merges both into a riffsheet and checks it.

Output, in the folder `build --out` names (without `--out`, in `out/` inside the scan folder):
- `riffsheet.md`: the account a person reads, beat by beat.
- `riffsheet.json`: the complete data (format in `schema/riffsheet.schema.json`).

## When to use it

- The user has the video as a file on this machine. For a link, ask them for the file; this tool does not download videos.
- The video is short: made for clips up to about a minute (it runs on longer ones with the overview spaced further apart, and past three minutes warns what will be slow).
- Needs ffmpeg 7 or newer and Python 3.9 or newer. Speech needs the optional `faster-whisper` package; without it, the analysis has no spoken lines unless a transcript is supplied.

## Commands

Change into this skill's folder (the repository root) and run from there, or give the full path to `scripts/riffsheet.py`. Type each command with its boxes and arguments written out: a command, box or argument list kept in a shell variable reaches the program as one word in zsh and fails. A shell function is fine and saves typing: define `rs` once as below, then use it for every command. Every command runs on any Python 3.9 or newer; only `transcribe` needs the `faster-whisper` package, so if that is installed in a virtual environment, define `rs` with that environment's Python. The ready-made commands the tool prints name the Python it ran under.

```
rs() { python3 -I scripts/riffsheet.py "$@"; }    # or: rs() { /path/to/venv/bin/python -I scripts/riffsheet.py "$@"; }
rs transcribe VIDEO --out T.json            # word-timed transcript (optional; needs faster-whisper)
rs scan VIDEO --out DIR --transcript T.json # measure everything; read DIR/summary.txt first
rs text DIR --box x0,y0,x1,y1 --name NAME   # each state of a caption or text region, with times
rs element DIR --box ROUGH --at T --name N  # measured box and times of a card, logo, sticker or pane
rs zoom DIR --at T [--box B]                # large sharp view, for clothing, products, small print
rs frames DIR --from S --to E [--box B]     # every frame of a window, for motion and order
rs mouth DIR --box B --words A-B            # is this person saying this line (its word range)
rs color DIR --at T --box B [--ref R]       # measured colors with plain names
rs build DIR                                # the sheet your judgment is written against
rs build DIR --judgment J.json --out OUT   # write and check the riffsheet into OUT
```

One folder per video keeps things apart. For `~/Downloads/ad.mp4`, a folder such as `~/riffsheet/ad/` holds `T.json` (the transcript), `scan/` (DIR: the tool's pictures and measurements; follow-up pictures land in `scan/look/`), `J.json` (your judgment) and `result/` (from `build ~/riffsheet/ad/scan --judgment ~/riffsheet/ad/J.json --out ~/riffsheet/ad/result`). Keep your own files out of the scan folder.

Boxes are fractions of the frame, `x0,y0,x1,y1`, `0,0` at the top left. Every time shown is the true time of that frame.

If the speech model is not on the machine, `transcribe` says so. Downloading it (about 500 MB, once) needs the user's go-ahead: then run `transcribe` with `--download`. Nothing else uses the network.

## How to do it

Follow `references/METHOD.md` from start to finish; read `references/TOOL.md` once for what each command prints and its limits. In short:

1. `transcribe`, `scan` and `build DIR` in one command. Without faster-whisper, run `scan` without `--transcript` (no spoken lines) or supply a transcript made another way.
2. Read the summary `scan` printed (no need to open `summary.txt` again), then open the overview sheets and any jump-cut sheet in one step.
3. In one step, read every caption region with `text`, measure every graphic with `element`, and take the `zoom`, `frames`, `mouth` and `color` views the overview calls for. A full-frame end card over a still picture gets its times from `element` but no box: give that box by eye.
4. Write the judgment file, taking pace words from the PACE block of the step 1 sheet and wrapping every statement that uses a word from its DETAIL WORDS list, and run `build DIR --judgment J.json --out OUT`.
5. For every statement it lists, open a large view of that moment, compare your words with it, and name the view in the statement's mark; rebuild until it prints `CHECKS: all passed`. Until then it writes no riffsheet. `build` checks that each statement names a close view of its moment; whether the words match the picture is yours to check.

Batch independent commands and images into one step: each step costs a full re-read of the conversation.

Then give the user `riffsheet.md`, and say what the analysis could not judge (anything that needs hearing).

## Making their own version

Section 11 of `references/METHOD.md` says what can be rebuilt with code or an editor, and where footage of people, places and products comes from: a camera or a video model. Riffkit (https://riffkit.ai/?utm_source=riffsheet&utm_medium=skill&utm_campaign=riffsheet&utm_content=skill_md) makes that footage from the original video.
