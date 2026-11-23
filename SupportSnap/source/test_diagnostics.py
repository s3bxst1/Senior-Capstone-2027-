"""Small checks for the behaviors that matter during the presentation."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from diagnostics import (analyze, baseline_age, collect_live, load_example,
                         make_report, recommend_solution)


def wifi_scores():
    """Run the named Wi-Fi sample with its original symptoms and date. Tests
    that change a reading load their own fresh copy instead.
    """
    case = load_example("wifi")
    return analyze(case, case["tags"], case["onset"])


def finding(rows, rule_id):
    """Return the finding or reading with the requested ID. Look it up by name
    because the position of a finding can change when another rule scores higher.
    """
    return next(row for row in rows if row["id"] == rule_id)


class DiagnosticTests(unittest.TestCase):
    def test_sample_driver_ranks_first(self):
        """Score the Wi-Fi sample as supplied. Its driver change and extra resets should
        put that explanation first with five points."""
        results = wifi_scores()
        self.assertEqual(results[0]["id"], "H01")
        self.assertEqual(results[0]["score"], 5)

    def test_before_onset_reduces_service_points(self):
        """Score the same service change with and without an onset date. Only the older
        configuration clue should lose half its points."""
        case = load_example("wifi")
        older = finding(analyze(case, ["Slow"], "2026-11-03"), "H02")
        unknown = finding(analyze(case, ["Slow"]), "H02")
        self.assertEqual(older["score"], 3)
        self.assertEqual(unknown["score"], 4)

    def test_contradictory_evidence_is_retained(self):
        """Check a case where one clue favors the add-in and another counts against it.
        Both explanations must remain visible even when the total is not positive."""
        case = load_example("wifi")
        addin = finding(analyze(case, ["Slow"], case["onset"]), "H03")
        self.assertTrue(addin["support"])
        self.assertTrue(addin["contradictions"])
        self.assertEqual(addin["status"], "Not supported")

    def test_refine_changes_candidate_set(self):
        """Narrow a mixed ticket to Wi-Fi symptoms only. The other categories should
        disappear from consideration."""
        results = analyze(load_example("wifi"), ["Internet / Wi-Fi"], "2026-11-03")
        self.assertEqual([c["id"] for c in results], ["H01"])

    def test_missing_evidence_never_becomes_a_cause(self):
        """Remove the readings needed for the driver rule. It should list both missing
        fields and give no points."""
        result = analyze(load_example("missing"), ["Internet / Wi-Fi"])[0]
        self.assertEqual(result["status"], "Insufficient evidence")
        self.assertEqual(result["score"], 0)
        self.assertEqual(len(result["missing"]), 2)

    def test_healthy_case_has_no_supported_cause(self):
        """Use the unchanged fictional baseline. The tool should not promote a cause just
        because someone reported a symptom."""
        case = load_example("healthy")
        self.assertFalse(any(c["status"] == "Possible cause" for c in analyze(case, case["tags"])))

    def test_unimplemented_symptoms_have_no_rules(self):
        """Select printing in a saved network example. No fictional rule should match
        that symptom."""
        self.assertEqual(analyze(load_example("wifi"), ["Printing"]), [])

    def test_low_storage_requires_both_limits(self):
        """Start with a low-space ticket, then raise only its free GiB. A low percentage
        alone should no longer qualify."""
        case = load_example("storage")
        self.assertEqual(analyze(case, ["Slow"])[0]["id"], "H07")
        finding(case["evidence"], "disk_free_gib")["current"] = 20
        storage = finding(analyze(case, ["Slow"]), "H07")
        self.assertNotEqual(storage["status"], "Possible cause")

    def test_declined_consent_does_not_read_drive(self):
        """Decline the scan while observing each collection entry point. None of the disk
        or operating system readers should be called."""
        with patch("live_checks.shutil.disk_usage") as disk, patch("live_checks.windows_values") as win, patch("live_checks.linux_values") as linux:
            with self.assertRaises(PermissionError):
                collect_live(False)
            disk.assert_not_called()
            win.assert_not_called()
            linux.assert_not_called()

    def test_live_data_does_not_include_sample_telemetry(self):
        """Give the collector only fixed drive readings. Check that it keeps the live
        source, leaves the baseline empty and never adds a fictional driver."""
        disk = SimpleNamespace(total=100*1024**3, free=5*1024**3)
        with patch("live_checks.shutil.disk_usage", return_value=disk), patch("live_checks.windows_values", return_value={}), patch("live_checks.linux_values", return_value={}):
            case = collect_live(True)
        self.assertEqual(case["origin"], "live")
        self.assertIsNone(case["baseline_at"])
        self.assertEqual(len(case["evidence"]), 8)
        self.assertNotIn("wifi_driver", {r["id"] for r in case["evidence"]})
        self.assertEqual(recommend_solution(analyze(case, ["Slow"]))["hypothesis_id"], "H07")

    def test_collection_failure_stays_missing(self):
        """Make the operating system and disk provide no usable readings. No performance
        rule should turn the missing values into a cause."""
        with patch("live_checks.shutil.disk_usage", side_effect=OSError("No reading")), patch("live_checks.windows_values", return_value={}), patch("live_checks.linux_values", return_value={}):
            case = collect_live(True)
        self.assertTrue(all(c["status"] == "Insufficient evidence" for c in analyze(case, ["Slow"])))

    def test_export_preserves_origin_and_notes(self):
        """Export a reviewed sample ticket. The report should keep its fictional label,
        technician note and review decision."""
        case = load_example("wifi")
        candidates = analyze(case, case["tags"], case["onset"])
        text, data = make_report(case, "Example statement", case["tags"], case["onset"],
                                 candidates, ["Check adapter logs next."], {"H01": "Needs follow-up"}, "LOCAL-TEST")
        self.assertIn("FICTIONAL SAMPLE DATA", text)
        self.assertIn("Check adapter logs next.", text)
        self.assertEqual(json.loads(json.dumps(data))["technician_reviews"]["H01"], "Needs follow-up")

    def test_baseline_age_is_computed(self):
        """Read the two dates bundled with the Wi-Fi sample. The result should be their
        12-day interval."""
        self.assertEqual(baseline_age(load_example("wifi")), 12)

    def test_recommendation_follows_scores_not_list_order(self):
        """Reverse the list of findings without changing their points. The driver should
        still provide the recommended check."""
        candidates = wifi_scores()
        recommendation = recommend_solution(list(reversed(candidates)))
        self.assertEqual(recommendation["hypothesis_id"], "H01")
        self.assertIn("driver", recommendation["solution"])
        self.assertTrue(recommendation["next_checks"])

    def test_symptom_refinement_changes_recommended_solution(self):
        """Keep only the slowdown symptom in the Wi-Fi ticket. The best remaining
        explanation should lead to the service check."""
        case = load_example("wifi")
        recommendation = recommend_solution(analyze(case, ["Slow"], case["onset"]))
        self.assertEqual(recommendation["hypothesis_id"], "H02")
        self.assertIn("service", recommendation["solution"])

    def test_ruled_out_leader_is_skipped_without_changing_points(self):
        """Rule out the leader and then its runner-up. Reviews should affect the
        recommendation while preserving the original scores."""
        candidates = wifi_scores()
        recommendation = recommend_solution(candidates, {"H01": "Ruled out"})
        self.assertEqual(recommendation["hypothesis_id"], "H02")
        self.assertEqual(candidates[0]["score"], 5)
        recommendation = recommend_solution(candidates, {"H01": "Ruled out", "H02": "Ruled out"})
        self.assertIsNone(recommendation["solution"])

    def test_storage_case_recommends_reviewed_cleanup(self):
        """Score the fictional low-storage case. The recommendation should ask a
        technician to review cleanup, not perform it automatically."""
        case = load_example("storage")
        recommendation = recommend_solution(analyze(case, case["tags"], case["onset"]))
        self.assertEqual(recommendation["hypothesis_id"], "H07")
        self.assertIn("Cleanup", recommendation["solution"])

    def test_new_addin_and_more_errors_can_lead_to_addin_recommendation(self):
        """Raise the application error count in a case with a new add-in. Those two clues
        together should lead to the Outlook check."""
        case = load_example("wifi")
        finding(case["evidence"], "app_errors")["current"] = 6
        recommendation = recommend_solution(analyze(case, ["Slow"], case["onset"]))
        self.assertEqual(recommendation["hypothesis_id"], "H03")
        self.assertIn("classic Outlook", recommendation["solution"])

    def test_equal_top_scores_do_not_choose_an_arbitrary_fix(self):
        """Give two causes equal positive scores. Both IDs and their checks should be
        reported without choosing a winner."""
        case = load_example("wifi")
        finding(case["evidence"], "disk_free_gib")["current"] = 5
        finding(case["evidence"], "disk_free_percent")["current"] = 2.5
        recommendation = recommend_solution(analyze(case, ["Slow"], None))
        self.assertEqual(set(recommendation["tied_ids"]), {"H02", "H07"})
        self.assertIsNone(recommendation["solution"])
        self.assertTrue(recommendation["next_checks"])

    def test_positive_but_weak_support_does_not_select_a_fix(self):
        """Keep only weak support for the driver explanation. A positive score below
        three should ask for more evidence."""
        case = load_example("wifi")
        driver = finding(case["evidence"], "wifi_driver")
        driver["current"] = driver["baseline"]
        candidates = analyze(case, ["Internet / Wi-Fi"], case["onset"])
        self.assertGreater(candidates[0]["score"], 0)
        recommendation = recommend_solution(candidates)
        self.assertIsNone(recommendation["solution"])
        self.assertIn("threshold", recommendation["reason"])

    def test_missing_healthy_and_unsupported_cases_do_not_select_fixes(self):
        """Try missing data, healthy data, and an empty list of rules. None justifies a
        proposed fix."""
        for key in ["missing", "healthy"]:
            with self.subTest(case=key):
                case = load_example(key)
                recommendation = recommend_solution(analyze(case, case["tags"], case["onset"]))
                self.assertIsNone(recommendation["solution"])
                self.assertTrue(recommendation["next_checks"])
        self.assertIsNone(recommend_solution([])["solution"])

    def test_export_recomputes_recommendation_after_review(self):
        """Rule out the driver before exporting. The report should name the service
        instead and agree with its JSON data."""
        case = load_example("wifi")
        candidates = analyze(case, case["tags"], case["onset"])
        text, data = make_report(case, "Example", case["tags"], case["onset"],
                                 candidates, [], {"H01": "Ruled out"}, "LOCAL-TEST")
        self.assertEqual(data["recommendation"]["hypothesis_id"], "H02")
        self.assertIn(data["recommendation"]["solution"], text)
        self.assertIn("RECOMMENDATION FROM RANKING", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
