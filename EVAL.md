# How accurate riffsheet is

This page says how the accuracy of a riffsheet was tested and what came out, including what the tests cannot tell you.

## When, and on what code

Tests 1 and 2 below were run on 2026-11-27, on development builds of the tool made before release 0.1.0. The code has changed since: it was reorganized, a jump cut inside one framing became a cut, and the tool now says where sound events fall on the cuts and caption appearances. Some of those changes came from these tests. The statement counts were not measured again on 0.1.0; the cut figures were (below, under [Measured on 0.1.0](#measured-on-010)).

Release 0.2.0 left the code that measures cuts, captions, stillness and loudness as it was in 0.1.0. It added the check of what the machine has, the record of each optional stage that ran, failed or did not run, and the hearing check. Nothing on this page was measured again on 0.2.0, and none of these tests covers what an agent says after passing the hearing check.

## What the tool does to stay accurate

- It measures what can be measured instead of estimating it by eye: cut times, the frame on which each caption appears and the frame on which it is gone, and whether the camera holds still, from the frames; loudness, word times and the pace of each line, from the sound.
- Every value in `riffsheet.json` says where it came from: measured by the tool, seen by the agent, heard by the agent (only after it passes the tool's hearing check), inferred, uncertain, established by the agent's own means, or not judged. Where the evidence does not settle a measurement, the value is left out with the reason.
- Statements about what people wear and hold, about products and about the place must each name a large view of a moment they describe (a movement may name a sheet of consecutive frames instead). Until every one does, or is marked uncertain, the tool writes no riffsheet. The tool checks that the view exists and shows that moment, not that the agent looked at it or that the words match it: that reading is the agent's, and the tests below are what measure it.
- What neither the pictures nor the measurements settle, such as tone of voice or what kind of music plays, is listed as not judged rather than guessed, unless the agent passed the hearing check and heard it.

## Test 1: statements checked against the frames

### What was tested

Ten short videos, 8 to 45 seconds long, in English, Chinese and Korean. They cover the common short-video formats: talking to the camera, product videos, screen recordings, outfit videos and fast-cut edits.

Each video was analyzed blind: a coding agent followed `references/METHOD.md` with the tool, starting from the video file alone, and produced a riffsheet.

Each riffsheet was then checked statement by statement against the video's frames by a separate agent that had not written it. Each statement was marked correct or wrong, and things the frames show that the riffsheet left out were counted as missed.

For two of the videos, cuts and captions were also checked against frame-by-frame ground truth.

### Results

| measure | result |
|---|---|
| statements judged across the ten videos | 649 correct, 23 wrong, 17 missed |
| hard cuts found (six videos checked for cuts) | 24 of 25, with no false cut |
| caption on and off times (two videos with frame-by-frame ground truth) | exact to the frame |
| agent time per video | about 4.5 to 8 minutes |

Of the statements made, about 97 in 100 were judged correct. The known measurement limits are listed at the end of `references/TOOL.md`.

## Test 2: a fact list made first, then the output scored against it

Test 1 starts from what the riffsheet says, so it cannot see what the riffsheet never mentions. This test starts from the video instead. Anyone can repeat it on any tool that describes videos:

1. Before looking at any output, build an inventory of checkable facts about the video from every one of its frames and from its sound: cut times, caption words and times, what each person wears and does, objects, the place, the camera, the spoken lines and their times. Each fact gets its time and the evidence that settles it (a frame, a measurement), and is worded so that it can be checked as true or false.
2. Score the tool's output fact by fact, wherever and however the output expresses each fact (prose, a table, a data field): stated exactly; stated partly or less precisely; contradicted; not mentioned; marked by the tool itself as uncertain; or left open by the tool.
3. Check every statement in the output that matches no fact against the frames. True ones become new facts on the list; false ones are counted as false statements.
4. Report how much of the list the output states, and of what it states outright, how much is right.

### Result

One 10.6-second video that had played no part in developing the tool, one run. The inventory held 116 facts; 21 more were added from true statements found while scoring, 137 in all.

| facts (137) | count |
|---|---|
| stated exactly | 64 |
| stated partly or less precisely | 36 |
| contradicted | 0 |
| not mentioned | 31 |
| marked by the tool as uncertain | 4 |
| left open | 2 |

Beyond the list, 3 statements were false. Of what it stated outright (facts stated exactly, facts contradicted and false statements), about 96 in 100 were right.

The changes this test led to are in this version; the numbers above are from the run before them.

## Measured on 0.1.0

On the code in this release:

| measure | result |
|---|---|
| hard cuts on the six videos of test 1 checked for cuts | 24 of 25 found, with no false cut (unchanged) |
| jump cuts inside one framing, on one 45-second talking video with 9 | 7 found as cuts, 2 not found |
| first runs by agents new to the project, on 5 videos (10, 19 and 45 seconds, and the two examples of 12 and 8 seconds) | each finished without help in about 4 to 8 minutes; not scored statement by statement |

Where sound events fall, as the tool measures it in the two examples (times only, not what the sound is):

| example | cuts on a loudness peak or rise | caption appearances on one |
|---|---|---|
| `examples/red-carpet` (12 s, edited to music) | 4 of 4, against about 0.9 by chance | 0 of 1, against about 0.1 by chance |
| `examples/outfit-rules` (8 s, spoken) | 0 of 3, against about 0.4 by chance | 4 of 5, against about 0.7 by chance |

What the agents in those two runs were unsure of, and where the tool misled them, is in each example's README.

## What these tests do not show

- The checking agents are the same kind of model as the agent that wrote the riffsheets. They can share its blind spots, and an error both miss is not counted.
- Anything that needs hearing was not scored in test 1: tone of voice, what kind of music plays, sound effects by name. The agents in these tests could not hear, so their riffsheets mark these as not judged. Since 0.2.0 an agent that passes the hearing check may describe the sound; how accurate that is has not been scored.
- Results vary from run to run, by a few statements per video.
- Ten videos is a small sample. Formats not in it may do better or worse.
- Test 2 is one video and one run, and its scorers are the same kind of model as the agent being scored. Facts are not weighted: a color and a cut time count the same.
