"""The Chinese README stays a translation of the English one: the same numbers and the same links."""

import os
import re
import unittest

from tests.clips import ROOT, read

EN = os.path.join(ROOT, "README.md")
ZH = os.path.join(ROOT, "README.zh-CN.md")
LINK = re.compile(r"""(?:\]\(|href="|src="|srcset=")([^)"\s]+)""")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def links(text):
    """Every link and image target, except a heading anchor (its words are translated) and the link
    from each README to the other. Tags for riffkit.ai name the Chinese placements with a zh_ prefix."""
    out = set()
    for t in LINK.findall(text):
        if t.startswith("#") or t in ("README.md", "README.zh-CN.md"):
            continue
        out.add(t.replace("utm_content=zh_", "utm_content="))
    return out


def numbers(text):
    return set(NUMBER.findall(text))


class Translation(unittest.TestCase):
    def test_same_links(self):
        en, zh = links(read(EN)), links(read(ZH))
        self.assertEqual(sorted(en - zh), [], "links in README.md missing from README.zh-CN.md")
        self.assertEqual(sorted(zh - en), [], "links in README.zh-CN.md not in README.md")

    def test_same_numbers(self):
        en, zh = numbers(read(EN)), numbers(read(ZH))
        self.assertEqual(sorted(en - zh), [], "numbers in README.md missing from README.zh-CN.md")
        self.assertEqual(sorted(zh - en), [], "numbers in README.zh-CN.md not in README.md")

    def test_chinese_tags_its_own_links(self):
        for url in re.findall(r"https://riffkit\.ai/\S+?(?=[\")\s])", read(ZH)):
            self.assertIn("utm_content=zh_", url)

    def test_each_links_the_other(self):
        self.assertIn('href="README.zh-CN.md"', read(EN))
        self.assertIn("README.md", read(ZH))


if __name__ == "__main__":
    unittest.main()
