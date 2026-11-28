# Changelog

The tool's version is printed by `python3 -I scripts/riffsheet.py --version`, with the version of the `riffsheet.json` format it writes (`format_version`).

## 0.2.0

The analysis says what this machine could and could not do for it, and never drops a stage silently.

- New `check [VIDEO] [--json]`, run before an analysis, no network: ffmpeg's version and any filter the tool needs that it lacks, and each optional capability (today speech recognition) as ready, missing or partly there (package installed but model not here, or installed only in `~/.riffsheet/venv`), with what it adds, what getting it costs (the faster-whisper package about 64 MB to download and 207 MB on disk, measured for 1.2.1 on Python 3.9 on macOS; the `small` model 486 MB) and the commands that prepare it in a virtual environment of its own, leaving the system Python as it is, and remove it again. With a video it says which pieces matter for it (speech recognition does not for a video without an audio track).
- Every optional stage ends in one of three recorded states: ran (and by what), failed (and why) or did not run (and why). `scan` writes them to `index.json` (`stages`), `build` to `riffsheet.json` (`_local.stages`), and when one failed or did not run, `riffsheet.md` says so under its first line. When `transcribe` cannot make a transcript it exits 1 as before and now also leaves at `--out` a record of why, which `scan --transcript` takes; an error inside the recognizer is reported in one line instead of a traceback.
- A video analyzed without speech recognition no longer reads as "no speech": the line under the title says `speech not transcribed`, `metadata.speaking_mode` is `none` tagged `cannot_judge_locally`, the scan summary and the build sheet say why there are no words and do not set loudness events against words, and a sentence in the prose or report saying that nobody speaks is a problem `build` lists.
- The instructions: the agent runs `check` first; when a missing piece matters for the video, it tells the person what it adds and costs and asks once, prepares it only on a yes, and otherwise carries on and says what the result lacks. It talks to the person in their language, and when they do not work in English it also writes a translation of `riffsheet.md` into their language beside it (`riffsheet.zh.md` and so on), with every time, number, spoken line and on-screen word unchanged; the checked files stay in English.
- `format_version` stays 1: everything added to `riffsheet.json` is optional (`_local.stages` is absent in files written before), and no field changed type or meaning; `_src.speaking_mode` uses a value the format already had.
- The two examples are rebuilt so that their `riffsheet.json` has `_local.stages`; the agents' words are unchanged.

## 0.1.0

First public release.

- `scan` measures a short video once: cuts on true frame timestamps, including a jump cut inside one framing when a tenth of the picture or more changes in one frame and keeps its colors; other changes, shot stillness, text-like regions, fixed layers, split layouts, drawn elements, and the sound (levels, silences, cliffs and peaks, what lies under the voice). It says where loudness peaks, rises and drops fall on the cuts, against how many would by chance (SOUND AT THE CUTS). It lays out the overview, one frame per shot, change events and possible jump cuts within a vision model's image budget.
- Follow-up commands for what an agent needs to look at: `text`, `element`, `zoom`, `frames`, `mouth` and `color`; the optional `transcribe` makes a word-timed transcript with faster-whisper.
- `build` prints the measured sheet a judgment is written against, and from the agent's judgment file writes `riffsheet.json` (format_version 1, `schema/riffsheet.schema.json`) and `riffsheet.md`, after checking the judgment against the measurements; statements about details must each name a view that shows them. It also says where sound events fall on the caption appearances, and puts both sound measures in `_local.sound_at_picture` and in one line of `riffsheet.md`.
- Exit status: 0 done, 1 an error, 2 a usage error, 3 a refused `build`.
- Python 3.9 or newer, standard library only; ffmpeg 7 or newer.
- Two examples, each a first run by an agent new to the project, with its commands, judgment file and pictures: `examples/red-carpet` (12 s, music, no speech) and `examples/outfit-rules` (8 s, Spanish to camera).
- A plugin marketplace file for Claude Code (`.claude-plugin/marketplace.json`).
