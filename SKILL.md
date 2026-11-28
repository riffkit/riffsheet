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
- Needs ffmpeg 7 or newer and Python 3.9 or newer. Spoken words need the optional `faster-whisper` package and its speech model; `check` says whether they are here and what getting them costs.

## Commands

Change into this skill's folder (the repository root) and run from there, or give the full path to `scripts/riffsheet.py`. Type each command with its boxes and arguments written out: a command, box or argument list kept in a shell variable reaches the program as one word in zsh and fails. A shell function is fine and saves typing: define `rs` once as below, then use it for every command. Every command runs on any Python 3.9 or newer; only `transcribe` needs the `faster-whisper` package, so if that is installed in a virtual environment, define `rs` with that environment's Python (`check` prints which one, as "run every riffsheet command with"). The ready-made commands the tool prints name the Python it ran under.

```
rs() { python3 -I scripts/riffsheet.py "$@"; }    # or: rs() { /path/to/venv/bin/python -I scripts/riffsheet.py "$@"; }
rs check VIDEO                              # what this machine can do, and what this video needs (no network)
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

Talk to the person in their language: every question, every report on progress, and the result.

## Before the analysis: what this machine can do

Run `rs check VIDEO` first, on the video you were given. It uses no network and changes nothing. Read its last line, `VERDICT`:

- **ffmpeg missing or lacking a filter**: tell the person what is missing; nothing can be analyzed until they install it.
- **ready for this video**: go on. A piece listed as not ready but not needed for this video (speech recognition for a video with no audio track) is not worth asking about.
- **ready under another Python**: define `rs` with the interpreter `check` names and go on; nothing needs installing.
- **a piece is not ready and matters for this video**: before anything else, ask the person once, in their language, whether to set it up. Say what it adds (its `adds` line), what the result will lack without it (its `without` line), and what it costs: each download's size in MB, the space on disk, that it needs the network, and where it goes (a virtual environment of its own in their home folder; the system Python is not changed). Take every number from `check`, never from memory. Then wait for the answer. Never install or download anything without a yes, and never carry on as if the piece were there.
  - **Yes**: run the commands `check` printed under "prepare it", in order (the model comes only with `transcribe --download`), define `rs` with the Python `check` named for afterwards, run `rs check VIDEO` again to see it ready, and go on.
  - **No**: go on without it. Tell the person once what the result will lack. Run `scan` without `--transcript`: the riffsheet then says the speech was not transcribed and why, and never that nobody speaks.

## How to do it

Follow `references/METHOD.md` from start to finish; read `references/TOOL.md` once for what each command prints and its limits. In short:

1. With speech recognition ready: `rs transcribe VIDEO --out T.json; rs scan VIDEO --out DIR --transcript T.json && rs build DIR` (a `;` after `transcribe`: if it fails, it leaves in T.json why, and `scan` records it, so the riffsheet says the speech recognition failed and why; tell the person). Without it: `rs scan VIDEO --out DIR && rs build DIR`, or `scan --transcript` with a transcript the person made another way.
2. Read the summary `scan` printed (no need to open `summary.txt` again), then open the overview sheets and any jump-cut sheet in one step.
3. In one step, read every caption region with `text`, measure every graphic with `element`, and take the `zoom`, `frames`, `mouth` and `color` views the overview calls for. A full-frame end card over a still picture gets its times from `element` but no box: give that box by eye.
4. Write the judgment file, taking pace words from the PACE block of the step 1 sheet and wrapping every statement that uses a word from its DETAIL WORDS list, and run `build DIR --judgment J.json --out OUT`.
5. For every statement it lists, open a large view of that moment, compare your words with it, and name the view in the statement's mark; rebuild until it prints `CHECKS: all passed`. Until then it writes no riffsheet. `build` checks that each statement names a close view of its moment; whether the words match the picture is yours to check.

Batch independent commands and images into one step: each step costs a full re-read of the conversation.

Then give the person `riffsheet.md`, or its translation into their language (below), and say what the analysis could not judge (anything that needs hearing) and anything that did not run (the paragraph **Not in this analysis** under its first line).

## The result in the person's language

`riffsheet.json` and `riffsheet.md` stay in English: they are what the tool's checks read. When the person is not working in English, after `build` prints `CHECKS: all passed`, write a translation for reading beside them, `riffsheet.<code>.md`, where `<code>` is the two-letter code of their language (`riffsheet.zh.md`, `riffsheet.es.md`, `riffsheet.ja.md`), and hand them that file. Rewrite it whenever `riffsheet.md` is rebuilt. It is your own writing: the tool neither writes nor checks it.

- The first line, in their language, says that it renders the checked English `riffsheet.md` beside it, which wins wherever the two differ (in Chinese, for example: 本文是同一文件夹里经过检查的英文版 riffsheet.md 的中文译本；两者不一致时，以 riffsheet.md 为准。).
- Everything in `riffsheet.md` is there, in the same order, in their language: the title line, the line under it, every paragraph, every heading (`What happens`, `Beat by beat`, `Keep when remaking` and the rest), every beat and every list item. Nothing is summarized, added or left out.
- Unchanged, character for character: every time and time range (`00:02.4–00:04.1`, `2.375 s`), every number with its unit (`-10 dB`, `0 of 3 cuts`, `8.042 s`, `0.052 s`), and every spoken line and on-screen word in quotation marks, which stay in the video's own language exactly as `riffsheet.md` gives them (spelling, case, punctuation). You may follow a quote with its meaning in their language in parentheses.
- Names of files, commands and fields (`riffsheet.json`, `zoom`) stay as they are; ordinary English words, the pace and measure words among them (`measured`, `brisk`, `locked`), are translated.

## Making their own version

Section 11 of `references/METHOD.md` says what can be rebuilt with code or an editor, and where footage of people, places and products comes from: a camera or a video model. Riffkit (https://riffkit.ai/?utm_source=riffsheet&utm_medium=skill&utm_campaign=riffsheet&utm_content=skill_md) makes that footage from the original video.
