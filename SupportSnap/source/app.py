"""SupportSnap desktop GUI. The packaged Windows app starts here."""

from datetime import date
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk
import uuid

from diagnostics import (SYMPTOMS, analyze, baseline_age, before_onset, collect_live,
                         display_pair, load_example, make_report, read_examples,
                         recommend_solution)
from live_checks import LIVE_LABEL, reference_from
from on_device import demo_tests, verify
BG, WHITE, INK, MUTED = "#f3f5f8", "#ffffff", "#182636", "#576578"
NAV, ACCENT, LINE, SOFT = "#182636", "#116c69", "#d8e0e8", "#e8f4f1"
FONT = "Segoe UI"


def packed(widget, **layout):
    """Place a widget and return it. Tk's own pack() returns None, so this small
    helper lets us create a widget, put it on screen, and keep it for later.
    """
    widget.pack(**layout)
    return widget


class SupportSnap(tk.Tk):
    def __init__(self):
        """Open the main window, choose fonts and colors, and load the list of demos. The
        default is a live check, but nothing is read until the user gives permission."""
        super().__init__()
        self.title("SupportSnap | Senior design prototype")
        self.geometry("1240x820")
        self.minsize(1040, 700)
        self.configure(bg=BG)
        global FONT
        available_fonts = set(tkfont.families(self))
        FONT = next((name for name in ["Segoe UI", "DejaVu Sans", "Liberation Sans", "Arial"] if name in available_fonts), "Helvetica")
        self.option_add("*Font", (FONT, 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", padding=7)
        style.configure("TProgressbar", background=ACCENT, troughcolor=LINE)
        style.configure("Treeview", font=(FONT, 10), rowheight=38,
                        background=WHITE, fieldbackground=WHITE, borderwidth=0)
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"),
                        background="#e9eef3", padding=9)
        style.map("Treeview", background=[("selected", "#d4ebe7")],
                  foreground=[("selected", INK)])
        self.samples = read_examples()
        self.examples = self.samples["cases"]
        self.choice_map = {LIVE_LABEL: "live", **{v["label"]: k for k, v in self.examples.items()}}
        self.choice = tk.StringVar(value=LIVE_LABEL)
        self.reference = None
        self.tags = {tag: tk.BooleanVar(value=False) for tag in SYMPTOMS}
        self.onset_text = tk.StringVar()
        self.consent = tk.BooleanVar(value=False)
        self.case = None
        self.notes, self.reviews, self.candidates = [], {}, []
        self.generation = 0
        self.evidence_filter = None
        self.show_input()

    def clear(self):
        """Remove the widgets from the current page. The case, notes and earlier scan
        stay in memory while the next screen is drawn."""
        for widget in self.winfo_children():
            widget.destroy()

    def frame(self, parent, bg=WHITE, **kwargs):
        """Make a plain container for related controls. Setting its background here keeps
        the pages consistent."""
        return tk.Frame(parent, bg=bg, **kwargs)

    def line(self, parent, text, size=10, bold=False, color=INK, wrap=0, **layout):
        """Place a line of text using the page colors and font. Most text lines
        start at the left; a header can set its own position with side.
        """
        if "side" not in layout:
            layout.setdefault("anchor", "w")
        label = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                         font=(FONT, size, "bold" if bold else "normal"),
                         anchor="w", justify="left", wraplength=wrap)
        return packed(label, **layout)

    def button(self, parent, text, command, primary=False, state="normal", **layout):
        """Place a button and connect it to the supplied action. Primary buttons
        have a different color; disabling Submit keeps consent visible in the form.
        """
        button = tk.Button(parent, text=text, command=command, state=state, relief="flat",
                           bg=ACCENT if primary else "#e9eef3", fg=WHITE if primary else INK,
                           activebackground="#cfe3df", activeforeground=INK, padx=15, pady=9,
                           cursor="hand2", font=(FONT, 10, "bold"))
        return packed(button, **layout)

    def card(self, parent, **kwargs):
        """Create the bordered panel used for a finding or a group of readings. The
        caller decides where the panel belongs on the page."""
        return self.frame(parent, highlightbackground=LINE, highlightthickness=1,
                          padx=18, pady=15, **kwargs)

    def split_view(self, parent, width, gap, bg):
        """Lay out a wide work area and a fixed sidebar. Both the hypothesis
        cards and the evidence table use this layout with different contents.
        """
        layout = packed(self.frame(parent, BG), fill="both", expand=True)
        rail = packed(self.card(layout, width=width), side="right", fill="y", padx=(gap, 0))
        rail.pack_propagate(False)
        left = packed(self.frame(layout, bg), side="left", fill="both", expand=True)
        return left, rail

    def scroll_area(self, parent, bg=BG):
        """Make a frame that can scroll when its contents do not fit. The canvas follows
        the window width so the controls inside still line up."""
        outer = packed(self.frame(parent, bg), fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
        scrollbar = packed(ttk.Scrollbar(outer, orient="vertical", command=canvas.yview), side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = self.frame(canvas, bg)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        def wheel(event):
            """Scroll this canvas one step in the direction of the mouse wheel. Ignore
            wheel events after the user leaves the page."""
            if canvas.winfo_exists():
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        canvas.bind("<Enter>", lambda event: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda event: canvas.unbind_all("<MouseWheel>"))
        canvas.bind("<Destroy>", lambda event: self.unbind_all("<MouseWheel>"))
        return inner

    def title_block(self, parent, title, subtitle):
        """Put a heading and a short explanation at the top of a page. Every screen uses
        the same spacing so the technician knows where to look."""
        self.line(parent, title, 23, True)
        self.line(parent, subtitle, color=MUTED, wrap=820, pady=(6, 18))

    def show_input(self):
        """Draw the form for a new ticket. It lists the live check beside the saved
        examples and asks for a description, symptoms and permission."""
        self.clear()
        header = packed(self.frame(self, NAV, padx=25, pady=15), fill="x")
        self.line(header, "SupportSnap", 20, True, WHITE, side="left")
        self.line(header, "SENIOR DESIGN  /  WORKING SKELETON", color="#b9c9d6", side="right")
        content = self.scroll_area(self)
        content.columnconfigure(0, weight=1)
        panel = self.card(content)
        panel.grid(row=0, column=0, sticky="n", padx=25, pady=24)
        self.title_block(panel, "What's going wrong?", "Describe a problem, approve a check, and review the evidence.")
        self.line(panel, "DEMONSTRATION OR LIVE CHECK", 9, True, MUTED)
        picker = packed(ttk.Combobox(panel, textvariable=self.choice, state="readonly",
                              values=list(self.choice_map), width=76), fill="x", pady=(6, 14))
        picker.bind("<<ComboboxSelected>>", lambda event: self.prefill())
        self.description_box = packed(tk.Text(panel, height=3, width=80, wrap="word", relief="solid",
                                       borderwidth=1, padx=10, pady=10, fg=INK, bg=WHITE), fill="x", pady=(0, 14))
        self.line(panel, "WHAT DOES IT FEEL LIKE?", 9, True, MUTED)
        tags = packed(self.frame(panel), fill="x", pady=(6, 14))
        for i, tag in enumerate(SYMPTOMS):
            tk.Checkbutton(tags, text=tag, variable=self.tags[tag], bg=WHITE, fg=INK,
                           activebackground=WHITE, selectcolor=SOFT).grid(row=i//3, column=i%3, sticky="w", padx=(0, 22))
        self.line(panel, "WHEN DID IT START?", 9, True, MUTED)
        ttk.Entry(panel, textvariable=self.onset_text, width=30).pack(anchor="w", pady=(6, 3))
        self.line(panel, "Enter YYYY-MM-DD, or leave blank if you are not sure.", color=MUTED)
        notice = packed(self.frame(panel, SOFT, padx=14, pady=12), fill="x", pady=(16, 10))
        self.notice = self.line(notice, "", wrap=680)
        tk.Checkbutton(panel, text="I approve this local check. Nothing will be sent to IT.",
                       variable=self.consent, bg=WHITE, selectcolor=SOFT,
                       command=self.update_submit).pack(anchor="w", pady=(3, 14))
        actions = packed(self.frame(panel), fill="x")
        self.submit = self.button(actions, "Submit & run check", self.start_check, True, state="disabled", side="left")
        self.button(actions, "Reset form", self.prefill, side="left", padx=10)
        self.button(actions, "Run demo tests", self.show_test_results, side="left")
        self.prefill()

    def prefill(self):
        """Fill the form from the selected mode and explain where the readings will come
        from. Changing modes or resetting the form always clears the earlier approval."""
        key = self.choice_map[self.choice.get()]
        if key == "live":
            description, tags, onset = "Check the live readings on this computer.", ["Slow"], ""
            note = "LIVE: reads CPU, RAM, drive space, uptime, active link count and Print Spooler state. No personal file contents, window titles or IP addresses are collected; no settings are changed."
            if self.reference:
                note += " Comparing with your session scan taken at " + self.reference["at"] + "."
        else:
            example = self.examples[key]
            description, tags, onset = example["description"], example["tags"], example["onset"]
            note = "SAMPLE DATA: loads fictional baseline and current readings to demonstrate comparisons and ranking. This mode does not scan your computer."
        self.fill_form(description, tags, onset)
        self.notice.configure(text=note)
        self.consent.set(False)
        self.update_submit()

    def fill_form(self, description, tags, onset):
        """Put the description, symptoms and optional date into the form. This
        also restores what the user typed when they request a comparison scan.
        """
        self.description_box.delete("1.0", "end")
        self.description_box.insert("1.0", description)
        self.onset_text.set(onset or "")
        for tag, variable in self.tags.items():
            variable.set(tag in tags)

    def selected_tags(self, choices=None):
        """Return the names of the checked symptoms. Use the ticket checkboxes by
        default, or pass the second set on the ranking screen."""
        return [tag for tag, variable in (choices or self.tags).items() if variable.get()]

    def update_submit(self):
        """Enable Submit only when the consent box is checked. The scan function checks
        consent again before doing any work."""
        self.submit.configure(state="normal" if self.consent.get() else "disabled")

    def start_check(self):
        """Check the ticket fields, then start collecting in the background so the window
        stays usable. When the readings arrive, run the ranking and show the summary."""
        if not self.consent.get():
            return
        self.statement = self.description_box.get("1.0", "end").strip()
        self.onset = self.onset_text.get().strip() or None
        if not self.statement or not self.selected_tags():
            messagebox.showinfo("A little more detail", "Add a description and select at least one symptom.")
            return
        try:
            if self.onset and date.fromisoformat(self.onset).isoformat() != self.onset:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Check the date", "Use YYYY-MM-DD, such as 2026-11-03, or leave it blank.")
            return
        key = self.choice_map[self.choice.get()]
        if key != "live" and self.onset and self.onset > self.samples["captured_at"][:10]:
            messagebox.showinfo("Check the date", "The sample readings are dated November 9, 2026. Use an onset on or before that date.")
            return
        self.notes, self.reviews = [], {}
        self.evidence_filter = None
        self.case_id = "LOCAL-" + uuid.uuid4().hex[:6].upper()
        self.generation += 1
        generation = self.generation
        self.clear()
        panel = packed(self.card(self), fill="both", expand=True, padx=60, pady=65)
        self.title_block(panel, "Checking your computer" if key == "live" else "Preparing the sample case",
                         "Reading local counters; unavailable checks stay marked." if key == "live" else "Fictional data is being loaded and compared. No device scan runs.")
        progress = packed(ttk.Progressbar(panel, maximum=6), fill="x", pady=(15, 24))
        stages = (["Collect local device counters", "Record available and missing values", "Match selected symptoms",
                   "Compare with any session reference", "Rank possible causes", "Prepare local results"] if key == "live" else
                  ["Load sample baseline", "Load sample current readings", "Match selected symptoms",
                   "Compare before and after", "Apply diagnostic rules", "Prepare local results"])
        labels = []
        for stage in stages:
            label = self.line(panel, "Waiting  |  " + stage, size=12, color=MUTED, pady=8)
            labels.append(label)
        self.button(panel, "Cancel", self.cancel_check, anchor="w", pady=24)
        results = queue.Queue()
        def collect():
            """Load the selected sample or collect an approved live snapshot. Put either
            the case or the error in the queue; only the main thread updates the
            window."""
            try:
                results.put((True, collect_live(True, self.reference) if key == "live" else load_example(key, self.samples)))
            except Exception as exc:
                results.put((False, str(exc)))
        threading.Thread(target=collect, daemon=True).start()
        def tick(step=0):
            """Look for the worker's result without blocking the window. Once it arrives,
            show progress, rank the explanations and open the summary unless the user
            canceled."""
            if generation != self.generation:
                return
            if step == 0:
                try:
                    success, value = results.get_nowait()
                except queue.Empty:
                    self.after(100, lambda: tick(0))
                    return
                if not success:
                    messagebox.showerror("Check could not finish", value)
                    self.show_input()
                    return
                self.case = value
            if step < len(stages):
                if step == 4:
                    self.candidates = analyze(self.case, self.selected_tags(), self.onset)
                labels[step].configure(text="Done  |  " + stages[step], fg=ACCENT)
                progress["value"] = step + 1
                self.after(230, lambda: tick(step + 1))
                return
            self.navigate("Summary")
        self.after(100, tick)

    def cancel_check(self):
        """Leave the progress screen and return to the form. The old scan number prevents
        a late result from opening the wrong case."""
        self.generation += 1
        self.show_input()

    def compare_live(self):
        """Keep this live scan as the reference for the next one. Restore the user's
        description and symptoms, then ask for permission to scan again."""
        self.reference = reference_from(self.case)
        tags = self.selected_tags()
        self.choice.set(LIVE_LABEL)
        self.show_input()
        self.fill_form(self.statement, tags, self.onset)

    def navigate(self, page):
        """Draw the shared sidebar and open the selected technician page. The banner
        shows whether the readings are live or fictional."""
        self.clear()
        sidebar = packed(self.frame(self, NAV, width=190), side="left", fill="y")
        sidebar.pack_propagate(False)
        self.line(sidebar, "SupportSnap", 15, True, WHITE, padx=18, pady=(25, 3))
        self.line(sidebar, "Technician workspace", color="#bac9d8", padx=18, pady=(0, 32))
        pages = {"Summary": self.summary_page, "Hypotheses": self.hypotheses_page,
                 "Evidence": self.evidence_page, "Report": self.report_page,
                 "Baselines": self.baseline_page, "Settings": self.settings_page}
        for name in pages:
            tk.Button(sidebar, text=name, command=lambda n=name: self.navigate(n), anchor="w",
                      padx=18, pady=12, relief="flat", cursor="hand2",
                      bg=ACCENT if name == page else NAV, fg=WHITE,
                      activebackground=ACCENT, activeforeground=WHITE).pack(fill="x", padx=8, pady=3)
        self.button(sidebar, "New check", self.show_input, side="bottom", fill="x", padx=15, pady=22)
        main = packed(self.frame(self, BG), side="left", fill="both", expand=True)
        bar = packed(self.frame(main, WHITE, padx=24, pady=13), fill="x")
        self.line(bar, self.case["device"], bold=True, side="left")
        self.line(bar, self.case_id, color=MUTED, side="right")
        status = packed(self.frame(main, SOFT if self.case["origin"] == "live" else "#fff3d9", padx=24, pady=8), fill="x")
        text = ("LIVE DEVICE DATA  |  Measured on this computer" if self.case["origin"] == "live" else
                "SAMPLE DATA  |  Fictional readings and dates; no device scan was performed")
        self.line(status, text, color=INK)
        self.body = packed(self.frame(main, BG, padx=24, pady=21), fill="both", expand=True)
        pages[page]()

    def summary_page(self):
        """Show the ticket, baseline and strongest findings that have not been ruled out.
        For a live case, the technician can inspect the readings or take another scan
        here."""
        self.title_block(self.body, "Ticket report summary", "A local case for review. Nothing has been submitted to a ticketing system.")
        content = self.scroll_area(self.body)
        row = packed(self.frame(content, BG), fill="x")
        row.columnconfigure(0, weight=3)
        row.columnconfigure(1, weight=2)
        statement = self.card(row)
        statement.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.line(statement, "USER STATEMENT", 9, True, MUTED)
        self.line(statement, self.statement, 12, wrap=450, pady=10)
        self.line(statement, "  /  ".join(self.selected_tags()), bold=True, color=ACCENT, wrap=450)
        self.line(statement, "Reported onset: " + (self.onset or "Not sure"), color=MUTED, pady=(8, 0))
        scan = self.card(row)
        scan.grid(row=0, column=1, sticky="nsew")
        self.line(scan, "SCAN & BASELINE", 9, True, MUTED)
        known = sum(r["current"] is not None for r in self.case["evidence"])
        self.line(scan, f"Readings available: {known} of {len(self.case['evidence'])}", 12, True, pady=10)
        age = baseline_age(self.case)
        self.line(scan, f"Baseline age: {age} days" if age is not None else "Baseline: not available", color=MUTED)
        if self.case["origin"] == "live":
            self.button(scan, "See all live readings", lambda: self.open_evidence(None), anchor="w", pady=4)
            self.button(scan, "Verify live readings", lambda: self.show_test_results(live=True), anchor="w", pady=4)
            self.button(scan, "Compare another live scan", self.compare_live, anchor="w", pady=4)
            for note in self.case.get("collection_notes", []):
                self.line(scan, note, color=MUTED, wrap=290)
        else:
            self.line(scan, "Earlier configuration changes get fewer points; a change is not proof.", wrap=300, color=MUTED, pady=10)
        self.recommendation_card(content, wrap=800)
        preview = packed(self.card(content), fill="x", pady=18)
        self.line(preview, "TOP HYPOTHESES", 9, True, MUTED, pady=(0, 8))
        supported = [c for c in self.candidates if c["status"] == "Possible cause"
                     and self.reviews.get(c["id"]) != "Ruled out"]
        if not supported:
            message = ("More evidence is needed before a cause can be suggested." if any(c["missing"] for c in self.candidates) else
                       "No supported finding from the available rules. Further troubleshooting is needed.")
            self.line(preview, message, 12, wrap=800, pady=12)
        for rank, c in enumerate(supported[:3], 1):
            self.line(preview, f"{rank}.  {c['label']}", 12, True, pady=(9, 2))
            self.line(preview, f"Rule support: {c['strength']}  |  {c['score']:g} points  |  Not a probability", color=MUTED)
        actions = packed(self.frame(content, BG), fill="x", pady=4)
        self.button(actions, "Open full hypotheses", lambda: self.navigate("Hypotheses"), True, side="left")
        self.button(actions, "Add note", self.add_note, side="left", padx=10)
        self.button(actions, "Open report", lambda: self.navigate("Report"), side="left")
        self.line(content, f"Session notes: {len(self.notes)}", color=MUTED, pady=12)

    def recommendation_card(self, parent, wrap):
        """Set out the title, reasoning and suggested action in one card. Both the
        summary and the full ranking use this same view."""
        card = packed(self.card(parent, bg=SOFT), fill="x", pady=(14, 0), padx=(0, 5))
        self.line(card, "RECOMMENDATION FROM RANKING", 9, True, ACCENT)
        self.recommendation_labels = []
        for size, bold in [(13, True), (10, False), (10, False)]:
            label = self.line(card, "", size, bold, wrap=wrap, pady=(7, 0))
            self.recommendation_labels.append(label)
        self.button(card, "Checks before a fix", self.show_recommendation_checks, anchor="w", pady=(10, 0))
        self.refresh_recommendation()

    def refresh_recommendation(self):
        """Ask the ranking code what to check next given the technician's latest reviews.
        Update the card in place so scrolling and review choices are preserved."""
        self.recommendation = recommendation = recommend_solution(self.candidates, self.reviews)
        values = [recommendation["title"], recommendation["reason"],
                  "Possible solution: " + recommendation["solution"] if recommendation["solution"]
                  else "No fix selected. Follow the checks below."]
        for label, value in zip(self.recommendation_labels, values):
            label.configure(text=value)

    def show_recommendation_checks(self):
        """Open the checks behind the recommendation currently on screen. This only
        displays instructions; it does not run them."""
        recommendation = self.recommendation
        text = [recommendation["title"], recommendation["reason"], "CHECK FIRST"]
        text.extend(recommendation["next_checks"])
        text += ["POSSIBLE SOLUTION", recommendation["solution"] or "More evidence is needed.",
                 "The app recommends an action; it does not perform a fix."]
        messagebox.showinfo("Ranked recommendation", "\n\n".join(text))

    def update_review(self, candidate_id, value):
        """Remember the technician's decision about one cause. Recompute the
        recommendation so a ruled-out cause cannot supply the next step."""
        self.reviews[candidate_id] = value
        self.refresh_recommendation()

    def hypotheses_page(self):
        """List the explanations in score order with the evidence for and against each
        one. The technician can change symptoms, open a reading or rule out a cause."""
        self.title_block(self.body, "Ranked hypotheses", "Rules show evidence for and against each possibility. Support levels are not certainty.")
        left, rail = self.split_view(self.body, 235, 15, BG)
        self.line(rail, "REFINE THE SYMPTOMS", 10, True, pady=(0, 8))
        self.refine_tags = {tag: tk.BooleanVar(value=var.get()) for tag, var in self.tags.items()}
        for tag in SYMPTOMS:
            tk.Checkbutton(rail, text=tag, variable=self.refine_tags[tag], bg=WHITE,
                           selectcolor=SOFT, anchor="w").pack(anchor="w", pady=2)
        self.line(rail, "Re-rank applies rules to the checked symptoms. The description is kept as context, not automatically interpreted.", wrap=190, color=MUTED, pady=13)
        self.button(rail, "Re-rank", self.rerank, True, fill="x")
        self.button(rail, "Open report", lambda: self.navigate("Report"), fill="x", pady=10)
        self.line(rail, "RULES ONLY\n\nThe top eligible score selects the suggestion.\n\nRuled-out causes are skipped. Scores stay unchanged.", wrap=190, color=MUTED, pady=12)
        scroll = self.scroll_area(left)
        self.recommendation_card(scroll, wrap=510)
        if not self.candidates:
            self.line(scroll, "No implemented rule matches these symptoms.", 12, wrap=520, pady=20)
        for i, c in enumerate(self.candidates, 1):
            card = packed(self.card(scroll), fill="x", pady=(13, 0), padx=(0, 5))
            self.line(card, f"{i}. {c['label']}", 13, True, wrap=510)
            self.line(card, f"{c['status']}  |  {c['strength']} support  |  {c['score']:g} points", color=ACCENT if c["score"] > 0 else MUTED, wrap=510, pady=(5, 9))
            for text in c["support"]:
                self.line(card, "For: " + text, wrap=510, pady=2)
            for text in c["contradictions"]:
                self.line(card, "Against: " + text, color=MUTED, wrap=510, pady=2)
            if c["missing"]:
                self.line(card, "Missing: " + ", ".join(c["missing"]), color="#9a5b00", wrap=510, pady=3)
            actions = packed(self.frame(card), fill="x", pady=(10, 0))
            self.button(actions, "View evidence", lambda ids=c["evidence_ids"]: self.open_evidence(ids), side="left")
            self.button(actions, "Suggested checks", lambda candidate=c: messagebox.showinfo("Suggested checks - no action is executed", "\n\n".join(candidate["next_checks"])), side="left", padx=8)
            review = ttk.Combobox(card, values=["Not reviewed", "Needs follow-up", "Ruled out"], state="readonly", width=23)
            review.set(self.reviews.get(c["id"], "Not reviewed"))
            review.pack(anchor="w", pady=(10, 0))
            review.bind("<<ComboboxSelected>>", lambda event, cid=c["id"], box=review: self.update_review(cid, box.get()))

    def rerank(self):
        """Read the revised symptom choices and score the same case again. This changes
        which rules are considered without taking another device reading."""
        selected = self.selected_tags(self.refine_tags)
        if not selected:
            messagebox.showinfo("Choose a symptom", "Select at least one symptom before re-ranking.")
            return
        for tag, var in self.tags.items():
            var.set(tag in selected)
        self.candidates = analyze(self.case, self.selected_tags(), self.onset)
        self.navigate("Hypotheses")

    def open_evidence(self, ids):
        """Open the evidence table with an optional list of reading IDs. A finding
        supplies its own IDs; an empty filter lets the technician browse all readings."""
        self.evidence_filter = ids
        self.navigate("Evidence")

    def evidence_page(self):
        """Put earlier and current readings side by side. The filters narrow the table,
        and selecting a row explains its timing and which rules used it."""
        self.title_block(self.body, "Evidence: baseline vs current", "Select a reading to see its date, context, and related rules.")
        filters = packed(self.frame(self.body, BG), fill="x", pady=(0, 12))
        category = tk.StringVar(value="All relevant")
        picker = packed(ttk.Combobox(filters, textvariable=category, state="readonly", width=19,
                              values=["All relevant"] + sorted({r["category"] for r in self.case["evidence"]})), side="left")
        show_all = tk.BooleanVar(value=self.case["origin"] == "live")
        left, right = self.split_view(self.body, 260, 14, WHITE)
        self.line(right, "ROW DETAIL", 10, True)
        detail = self.line(right, "Select an evidence row.", wrap=218, pady=15)
        self.button(right, "Copy to notes", lambda: self.copy_evidence_note(detail.cget("text")), anchor="w", pady=10)
        columns = ("category", "item", "baseline", "current", "timing")
        table = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        widths = [105, 164, 115, 115, 120]
        for key, width in zip(columns, widths):
            table.heading(key, text="Comparison" if key == "timing" and self.case["origin"] == "live" else key.title())
            table.column(key, width=width, minwidth=65, stretch=key == "item")
        vertical = packed(ttk.Scrollbar(left, command=table.yview), side="right", fill="y")
        horizontal = packed(ttk.Scrollbar(left, orient="horizontal", command=table.xview), side="bottom", fill="x")
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.pack(fill="both", expand=True)
        table.tag_configure("older", foreground="#68788a")
        table.tag_configure("missing", foreground="#9a5b00")
        relevant = {key for c in self.candidates for key in c["evidence_ids"]}
        rows = {r["id"]: r for r in self.case["evidence"]}
        def refresh(*_):
            """Redraw the table from the current filters. Missing values stay visible,
            and live pairs are compared at the same precision used to display them."""
            table.delete(*table.get_children())
            for key, row in rows.items():
                if self.evidence_filter and key not in self.evidence_filter:
                    continue
                if category.get() != "All relevant" and row["category"] != category.get():
                    continue
                if category.get() == "All relevant" and not show_all.get() and key not in relevant:
                    continue
                earlier, current = display_pair(row)
                old = before_onset(row, self.onset)
                timing = "Before onset" if old else row["changed_at"] or "No change date"
                if self.case["origin"] == "live":
                    if row["current"] is None or row["baseline"] is None:
                        timing = "No pair"
                    else:
                        timing = "Same" if earlier == current else "Changed"
                tag = "missing" if row["current"] is None else "older" if old else ""
                table.insert("", "end", iid=key, values=(row["category"], row["label"],
                    earlier, current, timing), tags=(tag,))
        def select(_):
            """Show the values and the related rule IDs for the selected row. Include the
            original context so the technician can copy a useful note."""
            if not table.selection():
                return
            row = rows[table.selection()[0]]
            earlier, current = display_pair(row)
            related = [c["id"] for c in self.candidates if row["id"] in c["evidence_ids"]]
            text = (f"{row['label']}\n\nBaseline: {earlier}\n"
                    f"Current: {current}\n\n"
                    f"Change date: {row['changed_at'] or 'Not recorded'}\n\n"
                    f"Rules: {', '.join(related) or 'Not used by the selected rules'}\n\n"
                    + ("Predates reported onset; related configuration-change points are reduced."
                       if before_onset(row, self.onset) else "Compare this observation with the user's symptoms. A difference alone is not proof."))
            if row.get("detail"):
                text += "\n\n" + row["detail"]
            detail.configure(text=text)
        def reset():
            """Clear the finding filter and show all available rows. This only changes
            what is visible in the table."""
            self.evidence_filter = None
            category.set("All relevant")
            show_all.set(True)
            refresh()
        tk.Checkbutton(filters, text="Show other readings", variable=show_all, command=refresh, bg=BG).pack(side="left", padx=10)
        self.button(filters, "Clear hypothesis filter", reset, side="left")
        picker.bind("<<ComboboxSelected>>", refresh)
        table.bind("<<TreeviewSelect>>", select)
        refresh()

    def copy_evidence_note(self, text):
        """Add the selected evidence details to the case notes. If nobody has selected a
        row yet, ask them to pick one first."""
        if text == "Select an evidence row.":
            messagebox.showinfo("Select a reading", text)
            return
        self.notes.append(text)
        messagebox.showinfo("Note added", "This evidence was added to the local report notes.")

    def add_note(self):
        """Ask for a short technician note and keep it with the case. Show the report
        afterward so the user can see how it will appear."""
        note = simpledialog.askstring("Technician note", "What should the next technician know?", parent=self)
        if note and note.strip():
            self.notes.append(note.strip())
            self.navigate("Report")

    def report_data(self):
        """Build the text and JSON versions of the open case. Both exports use the same
        symptoms, rankings, notes and review decisions."""
        return make_report(self.case, self.statement, self.selected_tags(), self.onset,
                           self.candidates, self.notes, self.reviews, self.case_id)

    def report_page(self):
        """Display the actual text that will be exported. The buttons save it locally,
        copy it, or let the technician add another note."""
        self.title_block(self.body, "Review & export report", "Review the content before saving. Notes and files stay local; there is no automatic ticket submission.")
        actions = packed(self.frame(self.body, BG), fill="x", pady=(0, 12))
        self.button(actions, "Save text report", lambda: self.save_report("txt"), True, side="left")
        self.button(actions, "Save JSON", lambda: self.save_report("json"), side="left", padx=10)
        self.button(actions, "Copy report", self.copy_report, side="left")
        self.button(actions, "Add note", self.add_note, side="left", padx=10)
        self.text_view(self.body, self.report_data()[0])

    def text_view(self, parent, contents):
        """Show long text with a scrollbar and keep it read-only. Reports and
        test results both use this viewer so they are easy to copy or inspect.
        """
        report_frame = packed(self.frame(parent), fill="both", expand=True)
        text = tk.Text(report_frame, wrap="word", relief="flat", bg=WHITE, fg=INK, padx=18, pady=14)
        scrollbar = packed(ttk.Scrollbar(report_frame, orient="vertical", command=text.yview), side="right", fill="y")
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(fill="both", expand=True)
        text.insert("1.0", contents)
        text.configure(state="disabled")

    def save_report(self, extension):
        """Ask the user to choose a file, then write the selected report format.
        Canceling leaves the disk untouched, and write errors are shown to the user."""
        path = filedialog.asksaveasfilename(parent=self, title="Save a reviewed local report",
                   defaultextension="." + extension, initialfile=self.case_id + "." + extension,
                   filetypes=[(extension.upper() + " file", "*." + extension)])
        if not path:
            return
        text, data = self.report_data()
        try:
            Path(path).write_text(text if extension == "txt" else json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc))
            return
        messagebox.showinfo("Report saved", "Saved to:\n" + path + "\n\nNothing was sent to IT.")

    def copy_report(self):
        """Put the reviewed text report on the clipboard. This is a manual way to paste
        the result into a ticket."""
        self.clipboard_clear()
        self.clipboard_append(self.report_data()[0])
        messagebox.showinfo("Copied", "The reviewed report is on the clipboard.")

    def baseline_page(self):
        """Show which two dates the case compares. A live case can keep its current
        values as the reference for another approved scan."""
        self.title_block(self.body, "Baseline reference", "The baseline is an earlier snapshot used to explain what changed.")
        card = packed(self.card(self.body), fill="x")
        age = baseline_age(self.case)
        self.line(card, "Baseline: " + (self.case["baseline_at"] or "Not available for this live check"), 12, True)
        self.line(card, "Current: " + self.case["captured_at"], color=MUTED, pady=8)
        if self.case["origin"] == "live":
            self.line(card, "A reference is an earlier reading, not proof the device was healthy.", wrap=820)
            self.button(card, "Compare another live scan", self.compare_live, anchor="w", pady=8)
        elif age is not None:
            self.line(card, f"Fictional baseline: {age} days before the sample scan. Pre-onset changes get less weight.", wrap=820)
        self.button(card, "Inspect baseline and current readings", lambda: self.open_evidence(None), True, anchor="w", pady=6)

    def show_test_results(self, live=False):
        """Display real-device verification or fixed demo tests in a small window.
        The summary gives the counts; the scrollable text shows exactly what ran.
        """
        summary, details = verify(self.case) if live else demo_tests()
        window = tk.Toplevel(self)
        window.title("SupportSnap | Test results")
        self.line(window, summary, 12, True, padx=12, pady=10)
        self.button(window, "Close", window.destroy, side="bottom", pady=6)
        self.text_view(window, details)

    def settings_page(self):
        """List what this prototype can measure, recommend and export. The notes also
        identify the limits of the classroom rules."""
        self.title_block(self.body, "Prototype scope", "What runs in this build, and what still needs development.")
        card = packed(self.card(self.body), fill="x")
        facts = ["Comparison demo: four fictional cases with baseline and current readings.",
                 "Live: CPU, RAM, space, uptime, local links and Print Spooler.",
                 "Ranking: live rules and fictional rules stay separate. Uptime alone is not a cause.",
                 "Recommendation: the unique top eligible score must be at least 3. Ties or weak support need more checks.",
                 "Review: ruled-out causes cannot supply the recommendation. No fix is executed.",
                 "Storage: 10 GiB AND 10% low; 15 GiB AND 15% adequate. These are draft limits.",
                 "Privacy: no automatic upload, background monitoring, or file-content collection.",
                 "Exports: local text and JSON after review. Session notes are lost when the app closes.",
                 "Future work: persistent baselines and evaluation with technicians."]
        for fact in facts:
            self.line(card, fact, wrap=820, pady=9)


if __name__ == "__main__":
    SupportSnap().mainloop()
