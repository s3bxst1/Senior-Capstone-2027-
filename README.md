@'
<h1 align="center">SupportSnap</h1>
<p align="center"><em>Evidence-based Windows diagnostics for IT technicians.</em></p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%2011-0078D4?logo=windows&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white">
  <img alt="PowerShell" src="https://img.shields.io/badge/PowerShell-5391FE?logo=powershell&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-orange">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

---

## Overview

"My PC is slow" is not a diagnosis. SupportSnap collects endpoint telemetry with the user's consent, compares it against a baseline, and gives the technician **competing hypotheses** with **supporting and contradicting evidence**, or says plainly when the evidence is **insufficient**.

## How it works

1. **Describe** - the user selects or describes the problem.
2. **Consent and scan** - the app explains what it collects and runs only after approval.
3. **Compare** - results are checked against a known-good baseline or peer profile.
4. **Hypothesize** - a rule-based engine scores candidate causes.
5. **Report** - the technician gets an HTML/JSON report with recommended next checks.

## Scope

| Area | Included |
|---|---|
| Platform | Windows 11, local desktop app |
| Categories | Network, performance, application issues |
| Checks | ~12-15 diagnostic checks |
| Output | HTML and JSON reports with review and redaction |

## Privacy

- Scans require explicit user approval.
- Reports are saved only where the user chooses and are never uploaded automatically.
- No background or secret monitoring; use on authorized devices only.

## Project structure

```
src/supportsnap/   Application code (collectors, engine, ui, reports)
powershell/        PowerShell diagnostic scripts
baselines/         Known-good baseline profiles (JSON)
lab/               VM lab notes and fault-injection scripts
tests/             Unit tests and benchmark harness
docs/              Design docs and decision records
```

## Getting started

```powershell
git clone https://github.com/<your-org>/SupportSnap.git
cd SupportSnap
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Roadmap

Tracked in [Milestones](../../milestones). Feature freeze: **March 14**, final delivery: **April 19**.

## Team

| Name | Role |
|---|---|
| Sean Brennan | UI/UX and Application Developer |
| Seth Colby | Lead Developer / Systems Engineer |
| Sebastian Tovar | QA, Documentation and Project Coordinator |

University of Cincinnati - School of Information Technology - Senior Design 2026-2027
'@ | Set-Content README.md -Encoding utf8

# ---------- .gitignore ----------
@'
__pycache__/
*.pyc
.venv/
venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/
*.spec
*.egg-info/
.vscode/
.idea/
# Real scan output can contain sensitive data
/reports-output/
*.scan.json
'@ | Set-Content .gitignore -Encoding utf8

# ---------- LICENSE (MIT; change if your advisor/university requires otherwise) ----------
$year = (Get-Date).Year
@"
MIT License

Copyright (c) $year Sean Brennan, Seth Colby, Sebastian Tovar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"@ | Set-Content LICENSE -Encoding utf8

# ---------- Templates ----------
@'
## What changed
<!-- One or two sentences -->

## Related issue
Closes #

## Checklist
- [ ] Reviewed by one other team member
- [ ] Test added, or manual check documented below
- [ ] No real usernames, hostnames, or IPs in committed files

## How I tested it
'@ | Set-Content .github/pull_request_template.md -Encoding utf8

@'
---
name: Task
about: A unit of planned work
labels: task
---

**Goal**

**Acceptance criteria**
- [ ]

**Notes / dependencies**
'@ | Set-Content .github/ISSUE_TEMPLATE/task.md -Encoding utf8

@'
---
name: Bug report
about: Something is not working
labels: bug
---

**What happened**

**Expected behavior**

**Steps to reproduce**
1.

**Environment** (Windows build, Python version, VM or physical)
'@ | Set-Content .github/ISSUE_TEMPLATE/bug_report.md -Encoding utf8

@'
# Decision Records

One short file per decision (`0001-baseline-strategy.md`, etc.): context, options, decision, date, who voted how.
'@ | Set-Content docs/decisions/README.md -Encoding utf8

# ---------- First commit and publish ----------
git add .
git commit -m "chore: initial project scaffold"

gh repo create $RepoName $visibility --source . --remote origin --push `
    --description "Evidence-based Windows diagnostic tool for IT technicians (UC Senior Design 2026-27)"

gh repo edit --add-topic python --add-topic powershell --add-topic windows `
    --add-topic diagnostics --add-topic help-desk --add-topic capstone --add-topic it-support

# ---------- Labels ----------
$labels = @(
    @("phase: design", "5319E7"), @("phase: environment", "1D76DB"), @("phase: diagnostics", "0E8A16"),
    @("phase: reports", "FBCA04"), @("phase: integration", "F9A825"), @("phase: testing", "D93F0B"),
    @("phase: finalize", "0052CC"),
    @("task", "C5DEF5"), @("collector", "BFD4F2"), @("engine", "D4C5F9"), @("ui", "F9D0C4"),
    @("qa", "FEF2C0"), @("docs", "C2E0C6"), @("blocked", "B60205"), @("bug", "D73A4A")
)
foreach ($l in $labels) { gh label create $l[0] --color $l[1] --force | Out-Null }

# ---------- Milestones (from the project plan) ----------
$milestones = @(
    @("Phase 3: System and UI Design", "2026-10-25"),
    @("Phase 4: Environment + Walking Skeleton", "2026-11-15"),
    @("Phase 5: Diagnostics v0", "2026-12-05"),
    @("Phase 6: Engine v1 + Reports", "2027-02-01"),
    @("Phase 7: Integration + Benchmark", "2027-02-22"),
    @("Phase 8: Testing + Tuning (Feature Freeze 3/14)", "2027-03-14"),
    @("Phase 9: Finalize + Deploy", "2027-04-19")
)
foreach ($m in $milestones) {
    gh api repos/{owner}/{repo}/milestones -f title="$($m[0])" -f due_on="$($m[1])T23:59:59Z" | Out-Null
}

Write-Host "Done. Opening repo..." -ForegroundColor Green
gh repo view --web
