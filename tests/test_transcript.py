"""Transcript helpers: word alignment for `transcribe --compare`, joining words, script tests."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from riffsheet_lib import transcript  # noqa: E402


class Align(unittest.TestCase):
    def test_same_words_pair_one_to_one(self):
        self.assertEqual(transcript._align(["a", "b"], ["a", "b"]), [(0, 0), (1, 1)])

    def test_substitution_insertion_and_deletion(self):
        self.assertEqual(transcript._align(["this", "is", "rift"], ["this", "is", "riff"]), [(0, 0), (1, 1), (2, 2)])
        self.assertEqual(transcript._align(["a", "c"], ["a", "b", "c"]), [(0, 0), (None, 1), (1, 2)])
        self.assertEqual(transcript._align(["a", "b", "c"], ["a", "c"]), [(0, 0), (1, None), (2, 1)])
        self.assertEqual(transcript._align([], ["x"]), [(None, 0)])

    def test_words_compare_without_case_or_punctuation(self):
        self.assertEqual(transcript._norm_word(" Riff’s,"), "riff's")


class Scripts(unittest.TestCase):
    def test_join_words(self):
        self.assertEqual(transcript.join_words(["你", "好", "world"]), "你好 world")
        self.assertEqual(transcript.join_words(["안녕", "하세요"]), "안녕 하세요")  # Hangul is spaced

    def test_the_three_script_tests(self):
        self.assertTrue(transcript.is_wide("你") and transcript.is_wide("한"))
        self.assertFalse(transcript.is_wide("a"))
        self.assertTrue(transcript.is_unspaced_script("你") and transcript.is_unspaced_script("カ"))
        self.assertFalse(transcript.is_unspaced_script("한"))
        self.assertTrue(transcript.counts_by_character("한") and transcript.counts_by_character("你"))
        self.assertFalse(transcript.counts_by_character("。"))


if __name__ == "__main__":
    unittest.main()
