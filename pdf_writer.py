"""
pdf_writer.py — Fills the byteWave biweekly PDF template at exact coordinates.

Uses PyMuPDF redaction-based text removal (preserves table borders/drawings)
and re-inserts text using Calibri font to match the template's native look.

Coordinate system: PyMuPDF uses (x, y) where y=0 is TOP of page.
Page size: 612 x 792 pt  (US Letter)
"""
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
import os

TEMPLATE = Path(__file__).parent / "biweeklyreport.pdf"
OUTPUT_DIR = Path(__file__).parent / "outputs"

# ── Font Configuration ──────────────────────────────────────────────────────
# Try to use Calibri (matches the template). Fall back to Helvetica.
CALIBRI_PATH = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "calibri.ttf"
CALIBRI_BOLD_PATH = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "calibrib.ttf"

FONT_SIZE = 10
BLACK = (0, 0, 0)


def _register_font(doc: fitz.Document):
    """Register Calibri as a custom font if available on the system."""
    if CALIBRI_PATH.exists():
        try:
            # We'll use the font by referencing the file directly in insert_text
            return str(CALIBRI_PATH)
        except Exception:
            pass
    return None


def _redact_text_area(page: fitz.Page, rect: tuple):
    """
    Remove text within a rectangle using redaction annotations.
    
    Redactions remove text/image content but PRESERVE vector drawings
    (table borders, lines, shapes). This is the key difference from
    the old white-rectangle approach.
    """
    r = fitz.Rect(*rect)
    # fill=False → no white rectangle painted over the area.
    # The background image (which has clean empty cells) shows through
    # naturally, making inserted text look like it was typed into the form.
    page.add_redact_annot(r, fill=False)


def _apply_all_redactions(page: fitz.Page):
    """
    Apply all pending redaction annotations.
    
    images=fitz.PDF_REDACT_IMAGE_NONE → don't touch images
    graphics=fitz.PDF_REDACT_LINE_ART_NONE → don't touch vector drawings (borders!)
    text=True → remove text content within the redacted areas
    """
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
    )


def _insert_text(page: fitz.Page, x: float, y: float, text: str,
                 font_path: str = None, fontsize: float = FONT_SIZE):
    """
    Insert text at position (x, y baseline) using Calibri if available.
    Text is placed directly on the page — no background, no border — 
    looks like it was naturally typed into the form field.
    """
    if font_path and Path(font_path).exists():
        # Use Calibri TTF for a native look
        page.insert_text(
            fitz.Point(x, y),
            str(text),
            fontfile=font_path,
            fontname="Calibri",
            fontsize=fontsize,
            color=BLACK,
        )
    else:
        # Fallback to built-in Helvetica
        page.insert_text(
            fitz.Point(x, y),
            str(text),
            fontname="helv",
            fontsize=fontsize,
            color=BLACK,
        )


def _insert_textbox(page: fitz.Page, rect: tuple, text: str,
                    font_path: str = None, fontsize: float = FONT_SIZE):
    """Insert wrapped text inside a rect using Calibri if available."""
    r = fitz.Rect(*rect)
    if font_path and Path(font_path).exists():
        page.insert_textbox(
            r, str(text),
            fontfile=font_path,
            fontname="Calibri",
            fontsize=fontsize,
            color=BLACK,
            align=0,  # left-align
        )
    else:
        page.insert_textbox(
            r, str(text),
            fontname="helv",
            fontsize=fontsize,
            color=BLACK,
            align=0,
        )


def _truncate(text: str, max_chars: int = 88) -> str:
    """Truncate text to fit in a single PDF row."""
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


# ── Field Coordinates ───────────────────────────────────────────────────────
# These define the VALUE AREAS inside each cell (inset from borders).
# Each tuple: (x0, y0, x1, y1) — the area to redact and where text goes.
# We inset ~3pt from the cell borders so grid lines are never touched.

# Header table: borders are at x=72, x=189.14, x=576.34
# Rows:  134.42–158.54 (Dept), 159.02–184.82 (Name), 185.30–209.42 (Project), 209.90–234.02 (Dates)
HEADER_VALUE_RECTS = {
    "department":    (192, 135, 573, 157),   # inner area of Dept row
    "employee_name": (192, 160, 573, 183),   # inner area of Name row
    "project_name":  (192, 186, 573, 208),   # inner area of Project row
    "dates_covered": (192, 211, 573, 233),   # inner area of Dates row
}

# Section 1 header: "TASKS PERFORMED FROM ___ to ___"
# The date values sit on the same line as the header text
SECTION1_DATE_RECTS = {
    "from":  (247, 254, 333, 272),
    "to":    (349, 254, 454, 272),
}

# Tasks Performed table: borders at x=72, x=119.66, x=574.54
# Row numbers "1","2","3" baselines: ~342, ~370, ~395
# Cell borders: top ~328.6, row-sep ~354, ~380, bottom ~406
TASK_ROWS = [
    {
        "redact": (121, 329, 572, 353),   # inside row 1 cell (border 328→354)
        "text_pos": (124, 342),            # baseline aligned with row number "1"
    },
    {
        "redact": (121, 355, 572, 379),   # inside row 2 cell (border 354→380)
        "text_pos": (124, 370),            # baseline aligned with row number "2"
    },
    {
        "redact": (121, 381, 572, 405),   # inside row 3 cell (border 380→406)
        "text_pos": (124, 395),            # baseline aligned with row number "3"
    },
]

# Remarks section: The underline area below "2. REMARKS"
REMARKS_RECT = (75, 433, 575, 462)

# Upcoming Tasks table: columns at x=72, x=110, x=409.5, x=578.3
# Row borders: y=535.03, 560.35, 585.70, 609.46
# Row number baselines: ~549, ~574, ~599
UPCOMING_ROWS = [
    {
        "task_redact": (112, 536, 408, 559),    # inside row 1 task cell
        "task_text_pos": (115, 549),             # baseline aligned with "1"
        "date_redact": (411, 536, 577, 559),    # inside row 1 date cell
        "date_text_pos": (420, 549),
    },
    {
        "task_redact": (112, 561, 408, 584),    # inside row 2 task cell
        "task_text_pos": (115, 574),             # baseline aligned with "2"
        "date_redact": (411, 561, 577, 584),    # inside row 2 date cell
        "date_text_pos": (420, 574),
    },
    {
        "task_redact": (112, 587, 408, 608),    # inside row 3 task cell
        "task_text_pos": (115, 599),             # baseline aligned with "3"
        "date_redact": (411, 587, 577, 608),    # inside row 3 date cell
        "date_text_pos": (420, 599),
    },
]

# Signature date — baseline must sit on the line (y=636) and side-by-side with signature image
SIGNATURE_DATE_RECT = (296, 620, 489, 650)
SIGNATURE_DATE_POS = (360, 636)


# ── PUBLIC API ──────────────────────────────────────────────────────────────

def fill_report(data: dict, signature_path: str = None) -> Path:
    """
    Fill biweeklyreport.pdf with `data` and return path to the saved file.

    Required keys in data:
        department, from_date, to_date  (MM/DD/YYYY strings)
        tasks_performed                 (list of 3 strings)
        upcoming_tasks                  (list of 3 dicts: {task, date})
    Optional:
        remarks                         (str)
        employee_name                   (str, default pre-filled in template)
        project_name                    (str, default pre-filled in template)
    """
    if not TEMPLATE.exists():
        raise FileNotFoundError(
            f"PDF template not found at: {TEMPLATE}\n"
            "Ensure 'biweeklyreport.pdf' is in the project root."
        )

    OUTPUT_DIR.mkdir(exist_ok=True)

    doc = fitz.open(str(TEMPLATE))
    page = doc[0]

    # Detect Calibri font
    font_path = _register_font(doc)

    # ── STEP 1: Mark all areas for redaction (text removal) ──────────────
    # This removes old/default text while PRESERVING table borders and lines.

    # Header fields — always redact the value area
    _redact_text_area(page, HEADER_VALUE_RECTS["department"])
    _redact_text_area(page, HEADER_VALUE_RECTS["dates_covered"])
    
    # Only redact name/project if we're replacing them
    emp_name = data.get("employee_name", "").strip()
    if emp_name:
        _redact_text_area(page, HEADER_VALUE_RECTS["employee_name"])

    proj_name = data.get("project_name", "").strip()
    if proj_name:
        _redact_text_area(page, HEADER_VALUE_RECTS["project_name"])

    # Section 1 dates
    _redact_text_area(page, SECTION1_DATE_RECTS["from"])
    _redact_text_area(page, SECTION1_DATE_RECTS["to"])

    # Tasks performed table — redact all 3 rows
    for row in TASK_ROWS:
        _redact_text_area(page, row["redact"])

    # Remarks
    remarks = data.get("remarks", "").strip()
    if remarks:
        _redact_text_area(page, REMARKS_RECT)

    # Upcoming tasks — redact all 3 rows
    for row in UPCOMING_ROWS:
        _redact_text_area(page, row["task_redact"])
        _redact_text_area(page, row["date_redact"])

    # Signature date
    _redact_text_area(page, SIGNATURE_DATE_RECT)

    # ── STEP 2: Apply all redactions at once ─────────────────────────────
    # This removes the text content but keeps vector drawings (table borders)
    _apply_all_redactions(page)

    # ── STEP 3: Insert new text (looks naturally typed into the form) ────

    # Header values — positioned within the cell, vertically centered
    _insert_text(page, 195, 149, data.get("department", "Development ( Risk Tech)"),
                 font_path=font_path, fontsize=10)

    if emp_name:
        _insert_text(page, 195, 175, emp_name,
                     font_path=font_path, fontsize=10)

    if proj_name:
        _insert_text(page, 195, 200, proj_name,
                     font_path=font_path, fontsize=10)

    # Dates Covered
    dates_str = f"{data['from_date']}  to  {data['to_date']}"
    _insert_text(page, 195, 225, dates_str,
                 font_path=font_path, fontsize=10)

    # Section 1 header dates — "TASKS PERFORMED FROM [date] to [date]"
    _insert_text(page, 250, 268, data["from_date"],
                 font_path=font_path, fontsize=10)
    _insert_text(page, 338, 268, "to",
                 font_path=font_path, fontsize=10)
    _insert_text(page, 370, 268, data["to_date"],
                 font_path=font_path, fontsize=10)

    # Tasks Performed
    tasks = data.get("tasks_performed", ["", "", ""])
    for i, row in enumerate(TASK_ROWS):
        txt = _truncate(tasks[i] if i < len(tasks) else "", 80)
        if txt and txt != "-":
            _insert_text(page, row["text_pos"][0], row["text_pos"][1], txt,
                         font_path=font_path, fontsize=10)

    # Remarks
    if remarks:
        _insert_textbox(page, REMARKS_RECT, _truncate(remarks, 120),
                        font_path=font_path, fontsize=10)

    # Upcoming Tasks
    upcoming = data.get("upcoming_tasks", [])
    for i, row in enumerate(UPCOMING_ROWS):
        if i >= len(upcoming):
            break
        item = upcoming[i]
        task_txt = _truncate(item.get("task", ""), 50)
        date_txt = item.get("date", "")

        if task_txt and task_txt != "-":
            _insert_text(page, row["task_text_pos"][0], row["task_text_pos"][1],
                         task_txt, font_path=font_path, fontsize=10)
        if date_txt:
            _insert_text(page, row["date_text_pos"][0], row["date_text_pos"][1],
                         date_txt, font_path=font_path, fontsize=10)

    # ── SIGNATURE ────────────────────────────────────────────────────────
    if signature_path and Path(signature_path).exists():
        # Correctly bound to just the left half of the __________ line
        # so it doesn't overlap the text to the left or the date to the right.
        sig_rect = fitz.Rect(230, 600, 310, 640)
        page.insert_image(sig_rect, filename=str(signature_path),
                          keep_proportion=True)

    # Stamp today's date next to the signature line
    today = datetime.today().strftime("%m/%d/%Y")
    _insert_text(page, SIGNATURE_DATE_POS[0], SIGNATURE_DATE_POS[1], today,
                 font_path=font_path, fontsize=10)

    # ── SAVE ─────────────────────────────────────────────────────────────
    safe_from = data["from_date"].replace("/", "")
    safe_to = data["to_date"].replace("/", "")
    out_path = OUTPUT_DIR / f"Report_{safe_from}_to_{safe_to}.pdf"
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()
    return out_path


# ── QUICK TEST ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dummy = {
        "department": "Development ( Risk Tech)",
        "from_date": "03/19/2026",
        "to_date": "04/01/2026",
        "employee_name": "Rohith Rudrapati",
        "project_name": "Modelone",
        "tasks_performed": [
            "Done q1 tests and worked on bugs and worked on on call support",
            "Completed sprint review and retrospective meetings",
            "Updated documentation for API endpoints",
        ],
        "remarks": "All sprint deliverables completed on schedule.",
        "upcoming_tasks": [
            {"task": "Continue work on q2 testing phase", "date": "04/08/2026"},
            {"task": "Complete and test project tasks", "date": "04/11/2026"},
            {"task": "Review and finalize project tasks", "date": "04/14/2026"},
        ],
    }
    path = fill_report(dummy)
    print(f"Test PDF saved -> {path}")
