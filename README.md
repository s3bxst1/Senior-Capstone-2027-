
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



