# Changelog

The tool's version is printed by `python3 -I scripts/riffsheet.py --version`, with the version of the `riffsheet.json` format it writes (`format_version`).

## 0.1.0

First public release.

- `scan` measures a short video once: cuts on true frame timestamps, including a jump cut inside one framing when a tenth of the picture or more changes in one frame and keeps its colors; other changes, shot stillness, text-like regions, fixed layers, split layouts, drawn elements, and the sound (levels, silences, cliffs and peaks, what lies under the voice). It says where loudness peaks, rises and drops fall on the cuts, against how many would by chance (SOUND AT THE CUTS). It lays out the overview, one frame per shot, change events and possible jump cuts within a vision model's image budget.
- Follow-up commands for what an agent needs to look at: `text`, `element`, `zoom`, `frames`, `mouth` and `color`; the optional `transcribe` makes a word-timed transcript with faster-whisper.
- `build` prints the measured sheet a judgment is written against, and from the agent's judgment file writes `riffsheet.json` (format_version 1, `schema/riffsheet.schema.json`) and `riffsheet.md`, after checking the judgment against the measurements; statements about details must each name a view that shows them. It also says where sound events fall on the caption appearances, and puts both sound measures in `_local.sound_at_picture` and in one line of `riffsheet.md`.
- Exit status: 0 done, 1 an error, 2 a usage error, 3 a refused `build`.
- Python 3.9 or newer, standard library only; ffmpeg 7 or newer.
- Two examples, each a first run by an agent new to the project, with its commands, judgment file and pictures: `examples/red-carpet` (12 s, music, no speech) and `examples/outfit-rules` (8 s, Spanish to camera).
- A plugin marketplace file for Claude Code (`.claude-plugin/marketplace.json`).
