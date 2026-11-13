"""Capture desktop screenshots of the Adjutant UI for the GitHub README.

Runs inside mcr.microsoft.com/playwright/python; the app must be reachable at
host.docker.internal:8010. Screenshots land in /shots (mounted docs/images).
"""

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://host.docker.internal:8010/ui/"
OUT = Path("/shots")

SHOTS = [
    ("facts", None, "01-facts-dashboard"),
    ("containment", "Containment", "02-containment-gate"),
    ("briefs", "Briefs", "03-briefs-gate"),
    ("clocks", "Clocks", "04-regulatory-clocks"),
    ("dispatch", "Dispatch", "05-dispatch-board"),
    ("bcp", "BCP", "06-bia-readiness"),
    ("handoff", "Handoff", "07-shift-handoff"),
    ("automation", "Auto", "08-automation-kill-switch"),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
        viewport={"width": 1600, "height": 900},
        device_scale_factor=2,
    )
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(1500)

    for _tab, button_text, name in SHOTS:
        if button_text:
            page.get_by_role("button", name=re.compile(button_text)).first.click()
            page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / f"{name}.png"))
        print(f"captured {name}.png")

    browser.close()
