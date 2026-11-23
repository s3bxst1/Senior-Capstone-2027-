"""Controlled regression tests. Use Verify live readings on a live Summary to check actual hardware."""

import json
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from diagnostics import analyze, load_example, make_report, recommend_solution
from live_checks import FIELDS, collect_live, reference_from, windows_values
from on_device import verify

NORMAL = dict(cpu_percent=20, ram_percent=60, ram_free_gib=6, uptime_hours=72, links_up=1, spooler="Running")

def snapshot(changes=None, reference=None, free=40):
    """Build a controlled device case through the real collector, replacing just its data
    sources with fixed values. This makes boundary tests repeatable without reading
    the test computer."""
    readings = dict(NORMAL, **(changes or {}))
    disk = SimpleNamespace(total=100 * 1024**3, free=free * 1024**3)
    fake_os = SimpleNamespace(name="nt", environ={"SystemDrive": "D:"})
    with patch("live_checks.os", fake_os), patch("live_checks.windows_values", return_value=readings), patch("live_checks.shutil.disk_usage", return_value=disk) as read_disk:
        case = collect_live(True, reference)
    read_disk.assert_called_once_with("D:\\")
    return case

def choose(case, tags):
    """Run the ranking and recommendation in the same order as the app. Each test can
    then focus on the readings it is changing."""
    return recommend_solution(analyze(case, tags))

class LiveCheckTests(unittest.TestCase):
    def test_all_fields_and_units_are_live_only(self):
        """Check the live case has the eight expected fields and six check groups. A
        first scan should have no baseline."""
        case = snapshot()
        self.assertEqual([r["id"] for r in case["evidence"]], list(FIELDS))
        self.assertEqual((case["modules"], case["origin"], case["baseline_at"]), (6, "live", None))
        self.assertTrue(all(r["baseline"] is None for r in case["evidence"]))

    def test_cpu_and_memory_compete(self):
        """Supply both high CPU and high memory readings. The higher CPU score should win
        and the reason should mention the runner-up."""
        case = snapshot({"cpu_percent": 97, "ram_percent": 93, "ram_free_gib": 3})
        result = choose(case, ["Slow"])
        self.assertEqual(result["hypothesis_id"], "L01")
        self.assertIn("97.0%", result["reason"])
        self.assertIn("L02 with 3", result["reason"])

    def test_equal_resource_scores_request_more_evidence(self):
        """Set CPU and memory to readings that earn three points each. The tool should
        report a tie instead of picking a fix."""
        case = snapshot({"cpu_percent": 90, "ram_percent": 92})
        result = choose(case, ["Slow"])
        self.assertEqual(set(result["tied_ids"]), {"L01", "L02"})
        self.assertIsNone(result["solution"])

    def test_zero_links_vs_unavailable(self):
        """Try zero, missing and normal link counts. Only zero supplies evidence of no
        active local link."""
        self.assertEqual(choose(snapshot({"links_up": 0}), ["Internet / Wi-Fi"])["hypothesis_id"], "L03")
        self.assertIsNone(choose(snapshot({"links_up": None}), ["Internet / Wi-Fi"])["solution"])
        self.assertIsNone(choose(snapshot(), ["Internet / Wi-Fi"])["solution"])

    def test_spooler_is_symptom_gated(self):
        """Try a stopped and a pending print service. The stopped state matters only when
        printing is one of the selected symptoms."""
        case = snapshot({"spooler": "Stopped"})
        self.assertEqual(choose(case, ["Printing"])["hypothesis_id"], "L04")
        self.assertIsNone(choose(case, ["Slow"])["solution"])
        self.assertIsNone(choose(snapshot({"spooler": "StartPending"}), ["Printing"])["solution"])

    def test_link_loss_and_recovery(self):
        """Compare fixed snapshots with a link up, down and restored. The network rule
        should score four only while the count is zero and the network symptom is
        selected."""
        before = snapshot()
        down = snapshot({"links_up": 0}, reference_from(before))
        result = choose(down, ["Internet / Wi-Fi"])
        self.assertEqual((result["hypothesis_id"], result["score"]), ("L03", 4))
        self.assertIn("0 local link(s)", result["reason"])
        self.assertIsNone(choose(down, ["Slow"])["solution"])
        recovered = snapshot(reference=reference_from(down))
        self.assertIsNone(choose(recovered, ["Internet / Wi-Fi"])["solution"])

    def test_uptime_is_only_context(self):
        """Give the case an unusually long uptime and otherwise normal readings. Uptime
        by itself should not recommend a fix."""
        self.assertIsNone(choose(snapshot({"uptime_hours": 8000}), ["Slow", "Printing", "Internet / Wi-Fi"])["solution"])

    def test_reject_invalid_sensor_values(self):
        """Pass invalid percentages, counts and a service name. The collector should mark
        them unavailable rather than scoring them."""
        case = snapshot({"cpu_percent": 101, "ram_percent": float("nan"), "links_up": -1, "spooler": "unknown"})
        values = {r["id"]: r["current"] for r in case["evidence"]}
        self.assertTrue(all(values[k] is None for k in ("cpu_percent", "ram_percent", "links_up", "spooler")))

    def test_blocked_backend_keeps_disk(self):
        """Simulate a timed-out Windows collector with an independent disk result. The
        warning should appear and a valid storage finding should survive."""
        os_stub = SimpleNamespace(name="nt", environ={"SystemDrive": "C:"})
        disk = SimpleNamespace(total=100 * 1024**3, free=3 * 1024**3)
        with patch("live_checks.os", os_stub), patch("live_checks.shutil.disk_usage", return_value=disk), patch("live_checks.windows_values", side_effect=subprocess.TimeoutExpired("PowerShell", 12)):
            case = collect_live(True)
        self.assertTrue(case["collection_notes"])
        self.assertEqual(choose(case, ["Slow"])["hypothesis_id"], "H07")

    def test_parser_and_timeout(self):
        """Give the Windows reader a JSON object and then an invalid list. It should
        accept only the object and use a timeout."""
        with patch("live_checks.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(NORMAL).encode())) as run:
            self.assertEqual(windows_values(), NORMAL)
            self.assertEqual(run.call_args.kwargs["timeout"], 12)
        with patch("live_checks.subprocess.run", return_value=SimpleNamespace(stdout=b"[]")), self.assertRaises(ValueError):
            windows_values()

    def test_samples_never_become_references_or_live_tests(self):
        """Pass a fictional case into both live-only paths. Neither a session baseline
        nor a hardware test may use it."""
        sample = load_example("wifi")
        with self.assertRaises(ValueError):
            reference_from(sample)
        with self.assertRaises(ValueError):
            verify(sample)

    def test_export_has_real_comparison_and_reason(self):
        """Compare two fixed CPU snapshots and export the second. The report should
        preserve both readings, their reference time, and the measured reason."""
        first = snapshot()
        case = snapshot({"cpu_percent": 96}, reference_from(first))
        tags = ["Slow"]
        text, data = make_report(case, "Laptop feels slow", tags, None, analyze(case, tags), [], {}, "LOCAL-TEST")
        self.assertIn("LIVE DEVICE DATA", text)
        self.assertIn("96.0%", text)
        row = next(r for r in data["evidence"] if r["id"] == "cpu_percent")
        self.assertEqual((row["baseline"], row["current"], data["baseline_at"]), (20, 96, first["captured_at"]))
