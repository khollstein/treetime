"""Block building: a job survives short interruptions."""

import unittest

from tests._helpers import FakeProject, at, seg
from core.blocks import BlockOptions, build_blocks
from core.matching import ProjectMatcher


LANE_COVE = FakeProject(1, "P-2842 — Lane Cove", project_number="P-2842")
ELM_ST = FakeProject(2, "P-3100 — Elm St", project_number="P-3100")
MATCHER = ProjectMatcher([LANE_COVE, ELM_ST])
OPTS = BlockOptions(gap_s=300, short_switch_s=60, min_block_s=60)


def build(segments, options=OPTS, covered=None):
    return build_blocks(segments, MATCHER, options, covered)


class ContinuityTest(unittest.TestCase):

    def test_short_unmatched_window_does_not_split_a_block(self):
        """Two minutes in Outlook between two hours on P-2842 is still P-2842."""
        result = build([
            seg(0, 60, "P-2842 Lane Cove.qgz", "qgis-bin.exe"),
            seg(60, 2, "Inbox — Outlook", "outlook.exe"),
            seg(62, 58, "P-2842 report.docx", "winword.exe"),
        ])
        self.assertEqual(len(result.blocks), 1)
        block = result.blocks[0]
        self.assertIs(block.project, LANE_COVE)
        self.assertEqual(block.start, at(0))
        self.assertEqual(block.end, at(120))
        self.assertEqual(block.bridged_s, 120)
        self.assertEqual(result.bridged_count, 1)

    def test_several_short_interruptions_collapse_into_one_block(self):
        result = build([
            seg(0, 30, "P-2842 plan.qgz"),
            seg(30, 3, "Inbox — Outlook", "outlook.exe"),
            seg(33, 20, "P-2842 notes.docx"),
            seg(53, 4, "Slack", "slack.exe"),
            seg(57, 25, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].end, at(82))
        self.assertEqual(result.bridged_count, 2)

    def test_long_unmatched_stretch_ends_the_block(self):
        result = build([
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 30, "Inbox — Outlook", "outlook.exe"),
            seg(90, 60, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(result.blocks), 2)
        self.assertEqual(result.blocks[0].end, at(60))
        self.assertEqual(result.blocks[1].start, at(90))

    def test_brief_idle_is_bridged_but_a_long_one_is_not(self):
        bridged = build([
            seg(0, 30, "P-2842 plan.qgz"),
            seg(30, 3, "", idle=True),
            seg(33, 30, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(bridged.blocks), 1)

        split = build([
            seg(0, 30, "P-2842 plan.qgz"),
            seg(30, 45, "", idle=True),
            seg(75, 30, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(split.blocks), 2)

    def test_offline_always_ends_the_block(self):
        """A sleeping computer is not a quick window switch."""
        result = build([
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 1, "Computer was locked / asleep", "(offline)", offline=True),
            seg(61, 60, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(result.blocks), 2)

    def test_a_real_switch_to_another_project_is_kept(self):
        result = build([
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 60, "P-3100 Elm St.docx"),
        ])
        self.assertEqual([b.project for b in result.blocks], [LANE_COVE, ELM_ST])

    def test_fleeting_glance_at_another_job_is_absorbed(self):
        result = build([
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 0.5, "P-3100 Elm St — Outlook", "outlook.exe"),
            seg(60.5, 60, "P-2842 plan.qgz"),
        ])
        self.assertEqual(len(result.blocks), 1)
        self.assertIs(result.blocks[0].project, LANE_COVE)

    def test_fleeting_glance_is_kept_when_it_dwarfs_its_neighbours(self):
        opts = BlockOptions(gap_s=300, short_switch_s=600, min_block_s=1)
        result = build_blocks([
            seg(0, 0.5, "P-2842 plan.qgz"),
            seg(0.5, 5, "P-3100 Elm St.docx"),
            seg(5.5, 0.5, "P-2842 plan.qgz"),
        ], MATCHER, opts)
        self.assertEqual([b.project for b in result.blocks],
                         [LANE_COVE, ELM_ST, LANE_COVE])

    def test_switch_absorption_can_be_disabled(self):
        opts = BlockOptions(gap_s=300, short_switch_s=0, min_block_s=1)
        result = build_blocks([
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 0.5, "P-3100 Elm St — Outlook", "outlook.exe"),
            seg(60.5, 60, "P-2842 plan.qgz"),
        ], MATCHER, opts)
        self.assertEqual(len(result.blocks), 3)

    def test_hole_in_the_recording_counts_against_the_bridge(self):
        """Treetime restarting mid-morning is a gap, not a free pass."""
        bridged = build([
            seg(0, 30, "P-2842 plan.qgz"),
            seg(32, 30, "P-2842 plan.qgz"),      # two minute hole
        ])
        self.assertEqual(len(bridged.blocks), 1)
        self.assertEqual(bridged.blocks[0].duration_s, 62 * 60)

        split = build([
            seg(0, 30, "P-2842 plan.qgz"),
            seg(120, 30, "P-2842 plan.qgz"),     # ninety minute hole
        ])
        self.assertEqual(len(split.blocks), 2)


class CoverageTest(unittest.TestCase):

    def test_existing_entries_are_carved_out(self):
        result = build(
            [seg(0, 120, "P-2842 plan.qgz")],
            covered=[(at(30), at(60))],
        )
        self.assertEqual(
            [(b.start, b.end) for b in result.blocks],
            [(at(0), at(30)), (at(60), at(120))],
        )

    def test_fully_covered_block_is_dropped(self):
        result = build(
            [seg(0, 60, "P-2842 plan.qgz")],
            covered=[(at(-10), at(70))],
        )
        self.assertEqual(result.blocks, [])

    def test_leftover_slivers_are_dropped(self):
        result = build(
            [seg(0, 60, "P-2842 plan.qgz")],
            covered=[(at(0.5), at(60))],
        )
        self.assertEqual(result.blocks, [])


class ThresholdTest(unittest.TestCase):

    def test_blocks_below_the_minimum_are_dropped(self):
        result = build([seg(0, 0.5, "P-2842 plan.qgz")])
        self.assertEqual(result.blocks, [])

    def test_nothing_matched_means_no_blocks(self):
        result = build([seg(0, 60, "Discover Weekly", "spotify.exe")])
        self.assertEqual(result.blocks, [])

    def test_empty_input(self):
        self.assertEqual(build([]).blocks, [])

    def test_no_projects(self):
        result = build_blocks([seg(0, 60, "P-2842 plan.qgz")],
                              ProjectMatcher([]), OPTS)
        self.assertEqual(result.blocks, [])

    def test_segments_are_sorted_before_grouping(self):
        result = build([
            seg(62, 58, "P-2842 report.docx"),
            seg(0, 60, "P-2842 plan.qgz"),
            seg(60, 2, "Inbox — Outlook", "outlook.exe"),
        ])
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].start, at(0))


if __name__ == "__main__":
    unittest.main()
