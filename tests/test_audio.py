"""Unit tests for the sound measures on hand-made level series (no video, no ffmpeg)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from riffsheet_lib import audio  # noqa: E402


def series(*parts):
    """100 ms blocks: (seconds, dB) parts in order. Returns (times, db)."""
    times, db = [], []
    for dur, level in parts:
        for _ in range(round(dur / 0.1)):
            times.append(round(len(times) * 0.1, 2))
            db.append(float(level))
    return times, db


def no_speech(t):
    return False


class Levels(unittest.TestCase):
    def test_silences_last_at_least_0_3_s(self):
        times, db = series((1.0, -20), (0.5, -60), (0.5, -20), (0.2, -60), (0.5, -20), (0.4, -60))
        self.assertEqual(audio.silences(times, db), [[1.0, 1.5], [2.7, 3.1]])

    def test_cliffs(self):
        times, db = series((1.0, -45), (1.0, -20), (1.0, -45))
        ev = audio.cliffs(times, db, no_speech)
        self.assertEqual(
            [(e["t"], e["type"], e["delta_db"]) for e in ev], [(1.0, "cliff_rise", 25.0), (2.0, "cliff_drop", -25.0)]
        )

    def test_peak_stands_above_both_sides(self):
        times, db = series((1.0, -30), (0.3, -12), (1.0, -30))
        ev = audio.peaks(times, db, no_speech)
        self.assertEqual(len(ev), 1)
        self.assertEqual(
            (ev[0]["t"], ev[0]["db"], ev[0]["delta_db"]), (1.1, -12.0, 18.0)
        )  # the sides count as no lower than -25
        flat = audio.peaks(*series((2.0, -20)), no_speech)
        self.assertEqual(flat, [])

    def test_level_words_and_energy_segments(self):
        self.assertEqual([audio.level_word(d) for d in (-50, -30, -20, -10)], ["silent", "low", "normal", "high"])
        times, db = series((0.3, -50), (0.2, -10))
        self.assertEqual(
            audio.energy_segments(times, db),
            [
                {"start": 0.0, "end": 0.3, "level": "silent", "rms_db": -50.0},
                {"start": 0.3, "end": 0.5, "level": "high", "rms_db": -10.0},
            ],
        )

    def test_half_second_levels(self):
        times, db = series((0.5, -20), (0.5, -40))
        self.assertEqual(audio.half_second_levels(times, db), [-20, -40])
        self.assertEqual(audio.half_second_levels([], []), [])

    def test_momentary_peaks(self):
        mom = [(k * 0.1, -30.0) for k in range(30)]
        mom[10] = (1.0, -20.0)
        mom[14] = (1.4, -20.0)  # too close to the first
        mom[25] = (2.5, -20.0)
        self.assertEqual(audio.momentary_peaks(mom), [1.0, 2.5])

    def test_speech_test(self):
        speech = audio.speech_test([{"start": 1.0, "end": 1.5}])
        self.assertTrue(speech(0.96) and speech(1.54))
        self.assertFalse(speech(0.9) or speech(1.6))


class LoudnessFacts(unittest.TestCase):
    def test_range_quietest_drops_and_sound_without_words(self):
        times, db = series((1.0, -20), (0.5, -50), (1.0, -20))
        speech = audio.speech_test([{"start": 0.0, "end": 1.0}])
        events = audio.cliffs(times, db, speech)
        f = audio.loudness_facts(times, db, speech, events)
        self.assertEqual(f["min"], [1.0, -50.0])
        self.assertEqual(f["max"][1], -20.0)
        self.assertIn([1.0, 1.3, -50.0], [q[:3] for q in f["quietest"]])
        self.assertEqual([d[1] for d in f["deepest_drops"]], [-50.0])
        self.assertEqual(f["sound_without_words"], [[1.5, 2.5, -20.0]])
        self.assertEqual(audio.loudness_facts([], [], speech, []), {})


class UnderVoice(unittest.TestCase):
    """pause_verdict on 20 ms levels: words at speech level, pauses at a chosen floor."""

    def levels(self, floor, pauses=4):
        db, words, t = [], [], 0.0
        for _ in range(pauses + 1):
            words.append({"start": round(t, 2), "end": round(t + 0.5, 2)})
            db += [-20.0] * 25 + [float(floor)] * 25
            t += 1.0
        return db, words

    def test_verdicts(self):
        self.assertEqual(audio.pause_verdict(*self.levels(-70))["verdict"], "no_continuous_bed")
        self.assertEqual(audio.pause_verdict(*self.levels(-30))["verdict"], "something_continues")
        self.assertEqual(audio.pause_verdict(*self.levels(-30, pauses=1))["verdict"], "too_few_pauses")
        r = audio.pause_verdict(*self.levels(-42))  # 22 dB under speech: neither near silence nor within 20 dB
        self.assertEqual((r["verdict"], r["silent"], r["continues"]), ("unclear", 0, 0))
        self.assertEqual(r["speech_db"], -20.0)

    def test_no_words(self):
        self.assertEqual(audio.under_voice(None, []), {"verdict": "no transcript", "pauses": []})
        self.assertEqual(audio.pause_verdict([], [{"start": 0.0, "end": 0.5}])["verdict"], "no audio under the words")


def ev(kind, onset, db=-10.0):
    return {"t": onset, "type": kind, "db": db, "delta_db": 10.0, "during_speech": False, "onset_t": onset}


class SoundAtPicture(unittest.TestCase):
    """sound_at and its chance baseline on hand-made onsets; refine_onsets on hand-made samples."""

    def test_on_off_and_nearest(self):
        events = [ev("peak", 1.0), ev("cliff_rise", 1.01), ev("cliff_drop", 2.5), ev("cliff_rise", 5.0)]
        changes = [
            {"id": "E1", "kind": "cut", "span": [1.02, 1.02]},  # on the peak; the rise 10 ms later is the same onset
            {"id": "E2", "kind": "cut", "span": [2.0, 2.0]},  # half a second before the drop
            {"id": "E3", "kind": "cut", "span": [3.6, 3.7]},  # nothing within 1 s
            {"id": "E4", "kind": "cut", "span": [4.9, 4.96]},  # a gradual change the rise lands just after
        ]
        r = audio.sound_at(changes, events, 0.043)
        self.assertEqual(r[0]["on"], [{"type": "peak", "t": 1.0, "dt": -0.02, "db": -10.0}])
        self.assertEqual((r[1]["on"], r[1]["nearest"]), ([], {"type": "cliff_drop", "t": 2.5, "dt": 0.5, "db": -10.0}))
        self.assertEqual((r[2]["on"], r[2]["nearest"]), ([], None))
        self.assertEqual([x["t"] for x in r[3]["on"]], [5.0])
        res = audio.sound_at_picture(changes, events, 0.043, 10.0)
        self.assertEqual(res["rises"], 2)
        self.assertTrue(audio.sound_at_summary(res).startswith("2 of 4 cuts land on a loudness peak or rise"))
        self.assertEqual(audio.sound_at_summary(audio.sound_at_picture([], events, 0.043, 10.0)), "no cuts to compare")

    def test_chance_baseline(self):
        # 19 rises, one every 0.5 s over 10 s, tolerance 0.05 s: a moment is within reach of one on 0.1 s
        # around each, so 3 changes land on one 3 x 19 x 0.1 / 10 times by chance (the drop does not count)
        events = [ev("cliff_rise", 0.5 * k) for k in range(1, 20)] + [ev("cliff_drop", 0.25)]
        self.assertAlmostEqual(audio.chance_on([[1.0, 1.0]] * 3, events, 0.05, 10.0), 3 * 19 * 0.1 / 10.0)
        # a change lasting 0.2 s reaches one from 0.3 s of every 0.5 s
        self.assertAlmostEqual(audio.chance_on([[1.0, 1.2]], events, 0.05, 10.0), 19 * 0.3 / 10.0)
        # overlapping reaches are joined, not added (0.95-1.09); a reach is cut at the clip's start
        dense = [ev("peak", 1.0), ev("peak", 1.04)]
        self.assertAlmostEqual(audio.chance_on([[0.0, 0.0]], dense, 0.05, 10.0), 0.14 / 10.0)
        self.assertAlmostEqual(audio.chance_on([[0.0, 0.0]], [ev("peak", 0.02)], 0.05, 10.0), 0.07 / 10.0)
        self.assertEqual(audio.chance_on([[1.0, 1.0]], [], 0.05, 10.0), 0.0)

    def test_refined_onsets(self):
        # 16 kHz: silence, a tone from 1.234 s to 1.6 s; the 100 ms curve puts the peak at 1.25 (blocks
        # 1.2-1.5 hold within 3 dB) and the rise at 1.3; both refine to the 10 ms block holding 1.234
        s = [0] * 19744 + [8000 if (i // 8) % 2 else -8000 for i in range(25600 - 19744)] + [0] * 8000
        events = [
            {"t": 1.35, "type": "peak", "db": -12.0, "_win": (1.2, 1.6)},
            {"t": 1.3, "type": "cliff_rise", "db": -12.0, "_win": (1.0, 1.4)},
            {"t": 1.7, "type": "cliff_drop", "db": -120.0, "_win": (1.4, 1.8)},
        ]
        audio.refine_onsets(events, s)
        self.assertEqual([e["onset_t"] for e in events], [1.23, 1.23, 1.6])
        self.assertNotIn("_win", events[0])
        none = [{"t": 1.0, "type": "peak", "db": -12.0, "_win": (0.9, 1.2)}]
        audio.refine_onsets(none, None)
        self.assertEqual(none[0]["onset_t"], None)


if __name__ == "__main__":
    unittest.main()
