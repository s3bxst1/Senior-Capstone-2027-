"""Rank explanations from measured evidence, then suggest what a technician can check."""

from operator import itemgetter

MIN_RECOMMENDATION_SCORE = 3
# Each rule lists its ID, display name, symptoms, required readings, and suggested checks.
SAMPLE_RULES = [
    ("H01", "Wi-Fi driver change may be related", {"Internet / Wi-Fi"},
     ["wifi_driver", "adapter_resets"],
     ["Review the adapter reset events and update date.",
      "Compare with a wired connection before changing settings."]),
    ("H02", "New startup service may be using resources", {"Slow"},
     ["startup_service", "cpu_percent"],
     ["Check the service's actual CPU use in Task Manager.",
      "Confirm whether the service is expected on this computer."]),
    ("H03", "Outlook add-in may be related to freezing", {"Slow", "Crashing"},
     ["outlook_addin", "app_errors"],
     ["Review Outlook events around the reported freeze.",
      "Ask whether the problem occurs in other applications."]),
    ("H07", "Low storage may be contributing", {"Slow", "Crashing", "Other"},
     ["disk_free_gib", "disk_free_percent"],
     ["Confirm the affected application uses this drive.",
      "Review storage needs before deciding on a fix."]),
]

LIVE_RULES = [
    ("L01", "CPU load may be slowing apps", {"Slow"}, ["cpu_percent"], ["Sort Task Manager by CPU during the slowdown."]),
    ("L02", "Memory pressure may be slowing apps", {"Slow", "Crashing"}, ["ram_percent", "ram_free_gib"], ["Compare available memory in Task Manager while the issue happens."]),
    ("H07", "The system drive may be short on space", {"Slow", "Crashing", "Other"}, ["disk_free_gib", "disk_free_percent"], ["Confirm the affected app writes to this drive."]),
    ("L03", "No active local network link was found", {"Internet / Wi-Fi"}, ["links_up"], ["Check the intended Wi-Fi or Ethernet connection."]),
    ("L04", "The print service may be blocking printing", {"Printing"}, ["spooler"], ["Check Print Spooler in Services before investigating the printer."]),
]

SOLUTIONS = {
    "H01": {
        "title": "Check the Wi-Fi driver first",
        "solution": "If testing links the issue to the driver update, have IT use an "
                    "approved replacement driver or available rollback, then retest Wi-Fi.",
    },
    "H02": {
        "title": "Check the new service's resource use first",
        "solution": "If the new service is confirmed to cause the high CPU use, have IT "
                    "adjust or update that service, then retest performance. "
                    "The overall CPU reading alone does not identify the process.",
    },
    "H03": {
        "title": "Check the Outlook add-in first",
        "solution": "For classic Outlook, test the suspected add-in separately. "
                    "If the issue is traced to it, have IT disable or update that add-in "
                    "and retest Outlook.",
    },
    "H07": {
        "title": "Review storage cleanup first",
        "solution": "If the affected application uses this drive, review Windows "
                    "Cleanup recommendations and remove only approved, unneeded files, "
                    "then recheck free space and the original problem.",
    },

    "L01": dict(title="Check CPU use first", solution="Identify the busy app and check whether the slowdown follows its workload."),
    "L02": dict(title="Check available memory first", solution="Identify the largest memory users and retest during normal use."),
    "L03": dict(title="Check the local link first", solution="Confirm the intended adapter is connected, then retest the original issue."),
    "L04": dict(title="Check the print service first", solution="Ask IT to verify why the spooler is not running before changing it."),
}

def before_onset(row, onset):
    """Check whether a dated change happened before the problem started. Without
    both dates we leave its points alone instead of guessing which happened first.
    """
    return bool(onset and row.get("changed_at") and row["changed_at"][:10] < onset)


def by_score(findings):
    """Put the highest point total first. Python leaves equal scores in their
    original order for display; the recommendation still treats them as a tie.
    """
    return sorted(findings, key=itemgetter("score"), reverse=True)


def observation(matches, points, why, why_not, row, onset=None):
    """Score one clue in a fictional before-and-after case. A match adds points
    and a contradiction subtracts them. An older configuration change earns half.
    Return the signed points with the exact reason the technician will see.
    """
    if not matches:
        return -points, f"{why_not} (-{points:g})"
    if before_onset(row, onset):
        points /= 2
        why += " This change predates onset, so its points are halved."
    return points, f"{why} (+{points:g})"


def low_space(free_gib, free_percent):
    """Flag low storage only when both limits are met. Real and sample cases
    use the same cutoff, even though the sample also scores adequate space.
    """
    return free_gib <= 10 and free_percent <= 10


def sample_clues(rule, rows, onset):
    """Compare the two readings named in a sample rule with their baselines.
    Each branch returns the clues for just that explanation. Storage uses two
    limits together; a value between the low and adequate limits is inconclusive.
    """
    a, b = rows
    if rule == "H01":
        return [
            observation(a["current"] != a["baseline"], 2.0, "Driver version changed from baseline.",
                        "Driver version matches baseline.", a, onset),
            observation(b["current"] > b["baseline"], 3.0, "Adapter reset events increased.",
                        "Adapter reset events did not increase.", b),
        ]
    if rule == "H02":
        return [
            observation(a["current"] and not a["baseline"], 2.0, "A startup service is newly present.",
                        "No new startup service is shown.", a, onset),
            observation(b["current"] >= 30 and b["current"] - b["baseline"] >= 15, 2.0,
                        "The CPU sample is elevated versus baseline.",
                        "The CPU sample does not meet the proposed increase limits.", b),
        ]
    if rule == "H03":
        return [
            observation(a["current"] and not a["baseline"], 2.0, "An Outlook add-in is newly present.",
                        "No new Outlook add-in is shown.", a, onset),
            observation(b["current"] > b["baseline"], 2.0, "Application error events increased.",
                        "Application error events did not increase.", b),
        ]
    if low_space(a["current"], b["current"]):
        return [(4, "Free space is at most 10 GiB AND at most 10%. (+4)")]
    if a["current"] >= 15 and b["current"] >= 15:
        return [(-4, "Free space is at least 15 GiB AND at least 15%. (-4)")]
    return [(0.0, "The proposed low-space limits are not both met. (0)")]


def live_clue(rule, rows):
    """Apply one simple rule to readings from this computer. Return points and a
    reason that includes the measured value. Zero means the reading does not
    support this explanation; an unavailable reading never reaches this function.
    """
    value = rows[0]["current"]
    if rule == "L01":
        score = 0 if value < 85 else 3 + int(value >= 95)
        return score, f"CPU measured {value:.1f}%; the demo flags 85% and gives one extra point at 95%."
    if rule == "L02":
        free = rows[1]["current"]
        score = 0 if value < 90 else 3 + int(free < 1)
        return score, f"Memory measured {value:.1f}% used with {free:.2f} GiB available; the demo flags 90%, plus one point below 1 GiB free."
    if rule == "H07":
        percent = rows[1]["current"]
        score = 4 if low_space(value, percent) else 0
        return score, f"The drive has {value:.2f} GiB ({percent:.1f}%) free; both must be at most 10 for this rule."
    if rule == "L03":
        return (4 if value == 0 else 0), f"{value} local link(s) reported up. Zero supports a link problem; this does not test Internet access."
    # The last live rule checks the Windows printing service.
    score = 4 if value in ("Stopped", "Paused") else 0
    return score, f"Print Spooler reported {value}; only Stopped or Paused supports this rule."


def support_level(score, missing):
    """Turn points into a short label for the screen and the report. A missing
    measurement is different from observing a value that scores zero.
    """
    if missing:
        return "Insufficient evidence", "Unavailable"
    if score <= 0:
        return "Not supported", "None"
    if score >= 5:
        return "Possible cause", "Strong"
    if score >= MIN_RECOMMENDATION_SCORE:
        return "Possible cause", "Moderate"
    return "Possible cause", "Weak"


def analyze(case, tags, onset=None):
    """Build the ranked list. Keep rules for the checked symptoms, find their
    readings, and score the rules that have enough evidence. Each finding keeps
    the reasons for and against it so someone can check the result themselves.
    """
    live = case["origin"] == "live"
    rules = LIVE_RULES if live else SAMPLE_RULES
    readings = {row["id"]: row for row in case["evidence"]}
    findings = []
    for rule, label, symptoms, fields, checks in rules:
        if not symptoms.intersection(tags):
            continue
        needs_baseline = not live and rule != "H07"
        missing = [key for key in fields if key not in readings or readings[key]["current"] is None
                   or (needs_baseline and readings[key]["baseline"] is None)]
        clues = []
        if not missing:
            rows = [readings[key] for key in fields]
            clues = [live_clue(rule, rows)] if live else sample_clues(rule, rows, onset)
        score = sum(points for points, reason in clues) if clues else (0 if live else 0.0)
        status, strength = support_level(score, missing)
        findings.append(dict(id=rule, label=label, score=score, status=status, strength=strength,
                             support=[reason for points, reason in clues if points > 0],
                             contradictions=[reason for points, reason in clues if points <= 0],
                             missing=missing, evidence_ids=fields, next_checks=checks,
                             source="Live rule" if live else "Rule"))
    return by_score(findings)


def recommend_solution(candidates, reviews=None):
    """Choose a next step from the scores, without changing any of them. A ruled-out
    cause cannot win. A tie, missing evidence for the leader, or a lead under three
    points is not enough to recommend a fix; return the checks to try instead.
    """
    reviews = reviews or {}
    active = [c for c in candidates if reviews.get(c["id"]) != "Ruled out"]
    ranked = by_score([c for c in active if c["status"] == "Possible cause"
                       and not c["missing"] and c["score"] > 0 and c["id"] in SOLUTIONS])
    result = {
        "status": "More checks needed", "hypothesis_id": None, "score": None,
        "title": "No supported solution yet", "reason": "",
        "solution": None, "next_checks": [], "tied_ids": [],
    }
    if not ranked:
        missing = sorted({key for c in active for key in c["missing"]})
        if missing:
            result["reason"] = "Required readings are missing. Collect more evidence before choosing a fix."
            result["next_checks"] = ["Collect: " + ", ".join(missing)]
        else:
            result["reason"] = "No remaining rule supports a cause for the selected symptoms."
            result["next_checks"] = ["Confirm the symptoms and collect evidence beyond the current rules."]
        observed = [c["contradictions"][0] for c in active if c.get("source") == "Live rule" and c["contradictions"]]
        if observed:
            result["reason"] += " " + " ".join(observed[:2])
        return result

    best = ranked[0]
    tied = [c for c in ranked if c["score"] == best["score"]]
    if len(tied) > 1:
        result.update(title="Top scores are tied", tied_ids=[c["id"] for c in tied],
                      reason=f"{', '.join(c['id'] for c in tied)} share {best['score']:g} points. "
                             "Check both possibilities before choosing a fix.",
                      next_checks=[f"{c['id']}: {check}" for c in tied for check in c["next_checks"]])
        return result
    if best["score"] < MIN_RECOMMENDATION_SCORE:
        result.update(title="The leading cause needs more evidence",
                      reason=f"{best['id']} leads with {best['score']:g} points, below the "
                             f"draft {MIN_RECOMMENDATION_SCORE}-point recommendation threshold.",
                      next_checks=list(best["next_checks"]))
        return result

    reason = f"{best['id']} has the highest eligible score: {best['score']:g} points."
    if len(ranked) > 1:
        reason += f" Next: {ranked[1]['id']} with {ranked[1]['score']:g} points."
    if best.get("source") == "Live rule" and best["support"]:
        reason += " " + best["support"][0]
    if any(c["missing"] for c in active):
        reason += " Another cause has missing readings, so this order may change."
    result.update(status="Recommended for review", hypothesis_id=best["id"],
                  score=best["score"], reason=reason, next_checks=list(best["next_checks"]),
                  **SOLUTIONS[best["id"]])
    return result
