"""Load the four fictional tickets and format reports for the technician."""

from copy import deepcopy
from datetime import date
import json
from pkgutil import get_data
from live_checks import collect_live
from ranking import analyze, before_onset, recommend_solution

SYMPTOMS = ["Slow", "Crashing", "Internet / Wi-Fi", "Can't sign in", "Printing", "Other"]


def read_examples():
    """Read the bundled JSON file containing the fictional cases and their common
    baseline. This does not collect anything from the device."""
    return json.loads(get_data(__name__, "demo_cases.json"))


def load_example(key, source=None):
    """Build a case by applying the selected example's changes to its fictional baseline.
    Return separate evidence rows so using one example never alters another."""
    if source is None:
        source = read_examples()
    example = deepcopy(source["cases"][key])
    current = {**source["baseline"], **example.pop("changes")}
    example.update(
        origin="sample", device="SUPPORT-LAB-01 (fictional)",
        platform="Windows 11 (sample)", baseline_at=source["baseline_at"],
        captured_at=source["captured_at"], scope="comparison_demo", modules=6,
    )
    example["evidence"] = [
        {"id": name, **details, "baseline": source["baseline"][name],
         "current": current[name], "changed_at": example["change_dates"].get(name)}
        for name, details in source["fields"].items()
    ]
    return example


def format_value(value, unit=""):
    """Turn a reading into short display text with its unit. Missing values stay
    unavailable, and numeric zero remains a real reading."""
    if value is None:
        return "Unavailable"
    if isinstance(value, bool):
        return "Present" if value else "Absent"
    if isinstance(value, float):
        value = f"{value:.2f}"
    return f"{value} {unit}" if unit else str(value)


def display_pair(row):
    """Format the baseline and current values the same way everywhere. Returning
    both strings keeps the evidence table and exported report in sync.
    """
    return format_value(row["baseline"], row["unit"]), format_value(row["current"], row["unit"])


def baseline_age(case):
    """Find the number of calendar days between two captures. Return None if the case has
    no previous scan."""
    if not case.get("baseline_at"):
        return None
    return (date.fromisoformat(case["captured_at"][:10]) -
            date.fromisoformat(case["baseline_at"][:10])).days


def make_report(case, description, tags, onset, candidates, notes, reviews, case_id):
    """Build a readable text report and matching JSON data from the same case. Recheck
    the recommendation against technician reviews and include evidence, notes and the
    data source."""
    recommendation = recommend_solution(candidates, reviews)
    data = {"prototype_version": "0.4-live-demo", "case_id": case_id, "origin": case["origin"],
            "device": case["device"], "captured_at": case["captured_at"],
            "baseline_at": case["baseline_at"], "statement": description,
            "symptoms": list(tags), "onset": onset, "scope": case["scope"],
            "evidence": deepcopy(case["evidence"]), "hypotheses": deepcopy(candidates),
            "recommendation": recommendation,
            "collection_notes": list(case.get("collection_notes", [])),
            "technician_reviews": dict(reviews), "notes": list(notes),
            "limitations": "Prototype rules; no proven root cause or measured time savings. "
                           "Recommendations require technician checks; no fix was performed. "
                           "Nothing was sent to a ticketing system."}
    text = ["SUPPORTSNAP - LOCAL REPORT", case_id,
            "FICTIONAL SAMPLE DATA" if case["origin"] == "sample" else "LIVE DEVICE DATA",
            f"Device: {case['device']}", f"Collected: {case['captured_at']}",
            f"Baseline: {case['baseline_at'] or 'Not available'}", "",
            "USER STATEMENT", description, f"Symptoms: {', '.join(tags)}",
            f"Onset: {onset or 'Not sure'}", "", "RECOMMENDATION FROM RANKING",
            recommendation["status"] + ": " + recommendation["title"],
            recommendation["reason"],
            "Possible solution: " + (recommendation["solution"] or "Not selected; more checks needed.")]
    text += ["Collection note: " + note for note in data["collection_notes"]]
    text += ["Check first: " + s for s in recommendation["next_checks"]]
    text += ["", "RULE FINDINGS"]
    for c in candidates:
        text += [f"{c['id']} - {c['label']}",
                 f"{c['status']} | Support: {c['strength']} | Points: {c['score']:g}",
                 "Review: " + reviews.get(c["id"], "Not reviewed")]
        text += ["For: " + s for s in c["support"]]
        text += ["Against: " + s for s in c["contradictions"]]
        if c["missing"]:
            text.append("Missing: " + ", ".join(c["missing"]))
        text += ["Next check: " + s for s in c["next_checks"]] + [""]
    if not candidates:
        text += ["No implemented rule matches the selected symptoms.", ""]
    text.append("EVIDENCE: BASELINE -> CURRENT")
    for row in case["evidence"]:
        earlier, current = display_pair(row)
        text.append(f"{row['label']}: {earlier} -> {current}")
    text += ["", "TECHNICIAN NOTES", *(notes or ["No notes added."]), "", data["limitations"]]
    return "\n".join(text), data
