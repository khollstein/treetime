"""Project matching: how a project number is written must not matter."""

import unittest

from tests._helpers import FakeProject
from core.matching import ProjectMatcher, build_keyword_pattern, keyword_score


class KeywordPatternTest(unittest.TestCase):

    def test_project_number_matches_any_separator(self):
        pattern = build_keyword_pattern("P-2842")
        for text in ("report p2842 final.docx",
                     "c:/jobs/p-2842 lane cove/plan.qgz",
                     "p 2842 inspection",
                     "p_2842"):
            self.assertIsNotNone(pattern.search(text), text)

    def test_project_number_respects_boundaries(self):
        pattern = build_keyword_pattern("P-2842")
        for text in ("p28421", "xp2842", "2842", "p284"):
            self.assertIsNone(pattern.search(text), text)

    def test_alphabetic_keyword_keeps_substring_behaviour(self):
        pattern = build_keyword_pattern("council")
        self.assertIsNotNone(pattern.search("north sydney councils - inbox"))

    def test_multiword_keyword_tolerates_separators(self):
        pattern = build_keyword_pattern("lane cove")
        self.assertIsNotNone(pattern.search("lane-cove report"))
        self.assertIsNotNone(pattern.search("Lane  Cove".lower()))

    def test_too_short_keyword_is_rejected(self):
        self.assertIsNone(build_keyword_pattern("a"))
        self.assertIsNone(build_keyword_pattern("  "))

    def test_project_numbers_outscore_equal_length_words(self):
        self.assertGreater(keyword_score("P-2842"), keyword_score("elmst"))


class ProjectMatcherTest(unittest.TestCase):

    def setUp(self):
        self.lane_cove = FakeProject(1, "P-2842 — Lane Cove", project_number="P-2842")
        self.council = FakeProject(2, "Council admin", keywords="council")
        self.matcher = ProjectMatcher([self.lane_cove, self.council])

    def test_matches_on_project_number_column(self):
        self.assertIs(
            self.matcher.match("qgis-bin.exe", "P2842 Lane Cove.qgz"),
            self.lane_cove,
        )

    def test_most_specific_keyword_wins(self):
        matcher = ProjectMatcher([
            FakeProject(1, "Generic", keywords="report"),
            FakeProject(2, "Specific", keywords="tree report 2026"),
        ])
        self.assertEqual(matcher.match("word.exe", "Tree Report 2026.docx").id, 2)

    def test_no_match_returns_none(self):
        self.assertIsNone(self.matcher.match("spotify.exe", "Discover Weekly"))

    def test_empty_matcher(self):
        self.assertTrue(ProjectMatcher([]).is_empty)
        self.assertIsNone(ProjectMatcher([]).match("x.exe", "anything"))


if __name__ == "__main__":
    unittest.main()
