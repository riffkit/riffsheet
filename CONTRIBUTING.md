# Contributing

Bug reports and fixes are welcome. Please open an issue first for a larger change, so we can agree on it before you write it.

## Running the tests

You need Python 3.9 or newer and ffmpeg 7 or newer built with libx264, freetype (the `drawtext` filter) and the lavfi test sources; the tests draw their own clips, so there are no video files in the repository. From the repository root:

```
RIFFSHEET_REQUIRE_FFMPEG=1 python3 -B -m unittest
```

`RIFFSHEET_REQUIRE_FFMPEG=1` turns a missing ffmpeg or filter into a failure; without it every test that needs ffmpeg is skipped and the run still says OK. The suite takes a minute or two. Lint and formatting use ruff (`ruff check scripts tests` and `ruff format --check scripts tests`; settings in `pyproject.toml`).

## Two rules

- **Standard library only.** The tool must run with nothing installed but Python and ffmpeg. A test checks every import. Only the optional `transcribe` command imports a package (faster-whisper), and only inside that command.
- **A refactor changes no output byte.** A change meant to keep behavior must leave every file the tool writes, every printed line and every exit status exactly as they were. A change that does alter output says exactly what changes in its commit message.

## The golden comparison

`tests/golden.py` runs a fixed sequence of commands on the test clips and records a hash of every output file and the exit status, stdout and stderr of every command. Record before your change and compare after it, from the same absolute folder with the same Python and the same ffmpeg (paths, the interpreter and the JPEG encoder all reach the outputs):

```
python3 -B tests/golden.py /tmp/rs-golden --write /tmp/before.json
# make the change
python3 -B tests/golden.py /tmp/rs-golden --compare /tmp/before.json
```

It prints `identical`, or each difference.

## Where things live

The procedure an agent follows is `references/METHOD.md`, and the command reference `references/TOOL.md`; a change in what the tool measures or prints usually needs a change there too. The code is the package `scripts/riffsheet_lib/` behind the entry script `scripts/riffsheet.py`; tuned thresholds are named constants with a comment saying why each has its value.
