"""common.py - helpers shared by the PRIN extraction modules.

Amounts are euros. The MUR PDFs write them Italian-style ("1.234,56").
"""
import re
import sys
import time

START = "https://prin.mur.gov.it/Pages/Index/301"


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def sector_of(name):
    m = re.search(r"(?<![A-Z0-9])(PE\d+|LS\d+|SH\d+|CYB)(?!\d)", name.upper())
    return m.group(1) if m else ""


def fetch_pdf(sess, url, dest, tries=3):
    """Download url to dest; only accept real PDFs (server sometimes returns HTML)."""
    if dest.exists() and dest.read_bytes()[:5] == b"%PDF-":
        return True
    for i in range(tries):
        try:
            r = sess.get(url, timeout=120,
                         headers={"Referer": START, "Accept": "application/pdf,*/*"})
            if r.ok and r.content[:5] == b"%PDF-":
                dest.write_bytes(r.content)
                return True
            print(f"  try {i+1}: {dest.name} -> HTTP {r.status_code}, "
                  f"{r.headers.get('content-type')}, not a PDF", file=sys.stderr)
        except Exception as e:
            print(f"  try {i+1}: {dest.name} -> {e}", file=sys.stderr)
        time.sleep(2 * (i + 1))
    return False
