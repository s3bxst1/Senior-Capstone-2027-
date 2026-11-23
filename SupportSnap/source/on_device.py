"""Six optional checks on the scan the presenter just approved; no fake readings."""

import io
import os
import shutil
import unittest
from live_checks import GIB, SPOOLER_STATES, system_drive

def verify(case):
    """Check the live readings that were just collected, then report how many passed,
    failed or were unavailable. Refuse sample data so these results always refer to
    the actual device."""
    if case.get("origin") != "live":
        raise ValueError("On-device tests require an approved live scan.")
    rows = {r["id"]: r["current"] for r in case["evidence"]}
    class ThisComputer(unittest.TestCase):
        def value(self, key):
            """Return one live value to its test. Skip the test if the operating system
            did not supply a value; do not count it as a pass."""
            if rows[key] is None:
                reason = "Windows only" if os.name != "nt" and key == "spooler" else "device did not supply a value"
                self.skipTest(f"{key}: {reason}; not verified.")
            return rows[key]

        def test_cpu_read(self):
            """Check the current CPU percentage is in range. A passing result verifies
            that reading, not the health of the processor."""
            self.assertTrue(0 <= self.value("cpu_percent") <= 100)

        def test_memory_pair(self):
            """Check both the measured memory percentage and the available GiB. A missing
            part makes the check unavailable."""
            self.assertTrue(0 <= self.value("ram_percent") <= 100)
            self.assertGreaterEqual(self.value("ram_free_gib"), 0)

        def test_drive_units_agree(self):
            """Use the system drive's capacity to convert the observed free GiB back into
            a percentage. The two displayed measurements should agree within rounding
            error."""
            total = shutil.disk_usage(system_drive()).total
            expected = self.value("disk_free_gib") * GIB * 100 / total
            self.assertAlmostEqual(expected, self.value("disk_free_percent"), delta=0.1)

        def test_boot_uptime(self):
            """Check the operating system reported a nonnegative time since boot. Uptime
            is context, not a diagnosis."""
            self.assertGreaterEqual(self.value("uptime_hours"), 0)

        def test_local_link_count(self):
            """Make sure the local link count is a nonnegative whole number. A genuine
            zero is a valid result and does not require sending network traffic."""
            count = self.value("links_up")
            self.assertTrue(type(count) is int and count >= 0)

        def test_print_service_read(self):
            """Check that Windows returned a known printing-service state. This test
            reads the state without starting the service or submitting a job."""
            self.assertIn(self.value("spooler"), SPOOLER_STATES)

    return test_output(unittest.defaultTestLoader.loadTestsFromTestCase(ThisComputer), live=True)


def test_output(suite, live=False):
    """Run the selected checks and collect readable results for the GUI. A
    skipped sensor is reported separately so an unavailable reading cannot pass.
    """
    output = io.StringIO()
    run = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    failed = len(run.failures) + len(run.errors)
    skipped = len(run.skipped)
    passed = run.testsRun - skipped - failed
    if live:
        summary = f"Device coverage: {passed}/{run.testsRun} verified; {skipped} unavailable; {failed} failed."
    else:
        summary = f"Demo tests: {passed}/{run.testsRun} passed; {skipped} skipped; {failed} failed."
    return summary, output.getvalue()


def demo_tests():
    """Run the fixed examples and scoring tests without scanning the computer.
    Use the same results view as live verification so the two are easy to compare.
    """
    suite = unittest.defaultTestLoader.loadTestsFromNames(["test_diagnostics", "test_live_checks"])
    return test_output(suite)
