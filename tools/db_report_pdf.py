#!/usr/bin/env python3
"""
Dwarfium Scope Archive — PDF Report Generator
Generates a statistics report from the DB, callable from the app or CLI.

Usage:
    python tools/db_report_pdf.py
    python tools/db_report_pdf.py --db path/to/db --out report.pdf
"""

import sqlite3
import re
import os
import sys
import argparse
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ── Colors ────────────────────────────────────────────────────────────────────
COLOR_PRIMARY   = colors.HexColor("#00ae83")
COLOR_DARK      = colors.HexColor("#1a1a2e")
COLOR_LIGHT_BG  = colors.HexColor("#f0faf7")
COLOR_GRAY      = colors.HexColor("#666666")
COLOR_RED       = colors.HexColor("#e74c3c")
COLOR_TABLE_HDR = colors.HexColor("#00ae83")
COLOR_TABLE_ALT = colors.HexColor("#f5fdf9")


# ── Styles ────────────────────────────────────────────────────────────────────





def _clean_obj_name(name: str, desc: str = None) -> str:
    """Format object name consistently for reports.
    - Uses description if available, truncated at first comma
    - Removes content in parentheses (type info)
    - Removes duplicate "in Constellation in Constellation" repetitions
    - Replaces underscores with spaces
    - Keeps [original_name] suffix
    """
    if not name:
        return name or ""
    import re as _re
    clean_name = name.replace("_", " ")
    if desc and desc.strip():
        desc_clean = desc.strip().split(",")[0]
        desc_clean = desc_clean.replace("_", " ")
        name_object = f"{desc_clean} [{clean_name}]"
    else:
        name_object = clean_name
    bracket_pos = name_object.rfind(" [")
    suffix = name_object[bracket_pos:] if bracket_pos != -1 else ""
    main_part = name_object[:bracket_pos] if bracket_pos != -1 else name_object
    # Remove content in parentheses
    main_part = _re.sub(r"\s*\([^)]*\)", "", main_part).strip()
    # Remove duplicate "in X in X" -> "in X"
    main_part = _re.sub(r"(\s+in\s+(\S+))\1+", r"\1", main_part).strip()
    if suffix and suffix.strip() not in main_part:
        return f"{main_part} {suffix}".strip()
    return main_part.strip()

    # Replace underscores with spaces in name
    clean_name = name.replace("_", " ")

    if desc and desc.strip():
        # Truncate at first comma
        desc_clean = desc.strip().split(",")[0]
        # Replace underscores
        desc_clean = desc_clean.replace("_", " ")
        name_object = f"{desc_clean} [{clean_name}]"
    else:
        name_object = clean_name

    # Extract suffix [name] if present
    bracket_pos = name_object.rfind(" [")
    suffix = name_object[bracket_pos:] if bracket_pos != -1 else ""
    main_part = name_object[:bracket_pos] if bracket_pos != -1 else name_object

    # Remove content in parentheses
    import re as _re
    main_part = _re.sub(r"\s*\([^)]*\)", "", main_part).strip()

    # Remove " in <Word>" suffix (constellation name)
    main_part = _re.sub(r"\s+in\s+\w+(\s+\w+)?$", "", main_part).strip()

    if suffix and suffix.strip() not in main_part:
        return f"{main_part} {suffix}".strip()
    return main_part.strip()


def build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Title"],
            fontSize=24, textColor=COLOR_PRIMARY,
            spaceAfter=6, alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontSize=11, textColor=COLOR_GRAY,
            spaceAfter=20, alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontSize=14, textColor=COLOR_PRIMARY,
            spaceBefore=16, spaceAfter=6,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=11, textColor=COLOR_DARK,
            spaceBefore=10, spaceAfter=4,
        ),
        "normal": ParagraphStyle(
            "normal", parent=base["Normal"],
            fontSize=9, textColor=COLOR_DARK,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"],
            fontSize=8, textColor=COLOR_GRAY,
            spaceAfter=2,
        ),
        "stat_label": ParagraphStyle(
            "stat_label", parent=base["Normal"],
            fontSize=9, textColor=COLOR_GRAY,
        ),
        "stat_value": ParagraphStyle(
            "stat_value", parent=base["Normal"],
            fontSize=12, textColor=COLOR_PRIMARY,
            fontName="Helvetica-Bold",
        ),
    }
    return styles


# ── DB helpers ────────────────────────────────────────────────────────────────
def connect(db_path):
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    return conn


def fmt_exp(total_sec):
    total_sec = total_sec or 0
    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    s = int(total_sec % 60)
    return f"{h}h {m:02d}m {s:02d}s"


def fmt_date(dt_str):
    if not dt_str:
        return "—"
    return str(dt_str)[:10]


# ── Report sections ───────────────────────────────────────────────────────────
def section_summary(conn, styles, story):
    story.append(Paragraph("Global Summary", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 8))

    totals = conn.execute("""
        SELECT
            COUNT(DISTINCT BE.id)               AS total_sessions,
            COUNT(DISTINCT BE.astro_object_id)  AS total_objects,
            SUM(DD.exp_time * DD.shotsStacked)  AS grand_total_sec,
            SUM(DD.shotsStacked)                AS grand_total_shots,
            MIN(BE.session_date)                AS first_session,
            MAX(BE.session_date)                AS last_session
        FROM BackupEntry BE
        JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
    """).fetchone()

    if not totals or not totals[0]:
        story.append(Paragraph("No backup data found.", styles["normal"]))
        return

    sessions, objects, total_sec, shots, first, last = totals

    data = [
        ["Total Sessions",    str(sessions or 0),
         "Total Objects",     str(objects or 0)],
        ["Total Shots",       str(shots or 0),
         "Total Exposure",    fmt_exp(total_sec)],
        ["First Session",     fmt_date(first),
         "Last Session",      fmt_date(last)],
    ]

    t = Table(data, colWidths=[4*cm, 4*cm, 4*cm, 5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("TEXTCOLOR",   (0, 0), (0, -1), COLOR_GRAY),
        ("TEXTCOLOR",   (2, 0), (2, -1), COLOR_GRAY),
        ("TEXTCOLOR",   (1, 0), (1, -1), COLOR_PRIMARY),
        ("TEXTCOLOR",   (3, 0), (3, -1), COLOR_PRIMARY),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME",    (3, 0), (3, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("FONTSIZE",    (1, 0), (1, -1), 11),
        ("FONTSIZE",    (3, 0), (3, -1), 11),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUND", (0, 0), (-1, -1), [COLOR_LIGHT_BG, colors.white]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cceecc")),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))


def section_drives(conn, styles, story):
    story.append(Paragraph("Backup Drives", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 8))

    drives = conn.execute("""
        SELECT BD.id, BD.name, BD.location, BD.last_backup_scan_date,
               D.name AS dwarf_name
        FROM BackupDrive BD
        LEFT JOIN Dwarf D ON BD.dwarf_id = D.id
        WHERE BD.location IS NOT NULL
        ORDER BY BD.id
    """).fetchall()

    if not drives:
        story.append(Paragraph("No backup drives configured.", styles["normal"]))
        return

    for did, name, loc, last_scan, dwarf_name in drives:
        online = os.path.exists(loc) if loc else False
        status_txt = "ONLINE" if online else "OFFLINE"
        status_col = COLOR_PRIMARY if online else COLOR_RED

        # Drive header
        hdr = Table([[
            Paragraph(f"<b>{name}</b>", styles["normal"]),
            Paragraph(f"[{dwarf_name or '?'}]", styles["small"]),
            Paragraph(f'<font color="#{status_col.hexval()[2:]}"><b>{status_txt}</b></font>',
                      styles["normal"]),
        ]], colWidths=[8*cm, 4*cm, 4*cm])
        hdr.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
            ("TEXTCOLOR",  (0, 0), (-1, -1), colors.white),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("ALIGN",      (2, 0), (2, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
        ]))
        story.append(hdr)

        # Drive stats
        stats = conn.execute("""
            SELECT
                COUNT(DISTINCT BE.id)                          AS sessions,
                COUNT(DISTINCT BE.astro_object_id)             AS objects,
                SUM(DD.exp_time * DD.shotsStacked)             AS total_sec,
                SUM(DD.shotsStacked)                           AS shots,
                MIN(BE.session_date)                           AS first,
                MAX(BE.session_date)                           AS last
            FROM BackupEntry BE
            JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
            WHERE BE.backup_drive_id = ?
        """, (did,)).fetchone()

        if stats and stats[0]:
            sessions, objects, total_sec, shots, first, last = stats
            info_data = [
                ["Location", loc or "—", "Sessions", str(sessions)],
                ["Last scan", fmt_date(last_scan), "Objects", str(objects)],
                ["First session", fmt_date(first), "Total shots", str(shots or 0)],
                ["Last session", fmt_date(last), "Exposure", fmt_exp(total_sec)],
            ]
            t = Table(info_data, colWidths=[3*cm, 9*cm, 3*cm, 2*cm])
            t.setStyle(TableStyle([
                ("FONTSIZE",  (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (0, -1), COLOR_GRAY),
                ("TEXTCOLOR", (2, 0), (2, -1), COLOR_GRAY),
                ("TEXTCOLOR", (3, 0), (3, -1), COLOR_PRIMARY),
                ("FONTNAME",  (3, 0), (3, -1), "Helvetica-Bold"),
                ("ROWBACKGROUND", (0, 0), (-1, -1), [COLOR_LIGHT_BG, colors.white]),
                ("GRID",  (0, 0), (-1, -1), 0.3, colors.HexColor("#ddeeee")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (0, -1), 6),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("  No sessions found for this drive.", styles["small"]))

        story.append(Spacer(1, 10))


def section_top_objects(conn, styles, story, string_number):
    story.append(Paragraph(f"Top {string_number} Objects by Exposure", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 8))

    limit = int (string_number)
    rows = conn.execute("""
        SELECT
            AO.name AS obj_name,
                    AO.description AS obj_desc,
            COUNT(DISTINCT BE.id)                    AS nb_sessions,
            SUM(DD.exp_time * DD.shotsStacked)       AS total_sec,
            SUM(DD.shotsStacked)                     AS shots,
            MIN(BE.session_date)                     AS first,
            MAX(BE.session_date)                     AS last
        FROM BackupEntry BE
        JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
        LEFT JOIN AstroObject AO ON BE.astro_object_id = AO.id
        GROUP BY BE.astro_object_id
        ORDER BY total_sec DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        story.append(Paragraph("No objects found.", styles["normal"]))
        return

    header = ["Object", "Sessions", "Shots", "Exposure", "First", "Last"]
    data   = [header]
    for obj_name, obj_desc, nb_sess, total_sec, shots, first, last in rows:
        obj_name = _clean_obj_name(obj_name, obj_desc)
        data.append([
            obj_name,
            str(nb_sess),
            str(shots or 0),
            fmt_exp(total_sec),
            fmt_date(first),
            fmt_date(last),
        ])

    # Wrap object names in Paragraph so they wrap within the cell
    small_style = ParagraphStyle("obj", fontSize=7, leading=9,
                                  textColor=COLOR_DARK)
    hdr_style   = ParagraphStyle("hdr", fontSize=8, leading=10,
                                  textColor=colors.white,
                                  fontName="Helvetica-Bold")
    wrapped = [[Paragraph(str(cell), hdr_style) if r == 0 and c == 0
                else Paragraph(str(cell), small_style) if c == 0
                else cell
                for c, cell in enumerate(row)]
               for r, row in enumerate(data)]

    t = Table(wrapped, colWidths=[7*cm, 1.8*cm, 1.8*cm, 3*cm, 2.2*cm, 2.2*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), COLOR_TABLE_HDR),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("ALIGN",        (0, 0), (0, -1), "LEFT"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUND",(0, 1), (-1, -1), [colors.white, COLOR_TABLE_ALT]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#cceecc")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (0, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))


def section_sessions_error(conn, styles, story):
    if not _table_exists(conn, "DwarfSessionsError"):
        return

    errors   = conn.execute(
        "SELECT COUNT(*) FROM DwarfSessionsError WHERE status='ERROR'"
    ).fetchone()[0]
    repaired = conn.execute(
        "SELECT COUNT(*) FROM DwarfSessionsError WHERE status='REPAIRED'"
    ).fetchone()[0]

    if errors == 0 and repaired == 0:
        return

    story.append(Paragraph("Sessions with Errors", styles["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 8))

    summary = Table([
        ["ERROR (missing stacked)", str(errors),
         "REPAIRED", str(repaired)],
    ], colWidths=[6*cm, 2*cm, 4*cm, 2*cm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("TEXTCOLOR",   (1, 0), (1, 0), COLOR_RED),
        ("TEXTCOLOR",   (3, 0), (3, 0), COLOR_PRIMARY),
        ("FONTNAME",    (1, 0), (1, 0), "Helvetica-Bold"),
        ("FONTNAME",    (3, 0), (3, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary)

    if errors > 0:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Unrepaired error sessions:", styles["h2"]))
        err_rows = conn.execute("""
            SELECT SE.session_date, SE.session_dir, D.name
            FROM DwarfSessionsError SE
            LEFT JOIN Dwarf D ON SE.dwarf_id = D.id
            WHERE SE.status = 'ERROR'
            ORDER BY SE.session_date DESC
            LIMIT 20
        """).fetchall()

        edata = [["Date", "Session Directory", "Dwarf"]]
        for date, session_dir, dwarf_name in err_rows:
            edata.append([fmt_date(date), session_dir or "—", dwarf_name or "—"])

        t = Table(edata, colWidths=[2.5*cm, 12*cm, 3*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), COLOR_RED),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 7),
            ("ROWBACKGROUND",(0, 1), (-1, -1), [colors.white, colors.HexColor("#fff0f0")]),
            ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#ffcccc")),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("LEFTPADDING",  (0, 1), (1, -1), 4),
        ]))
        story.append(t)

    story.append(Spacer(1, 12))


def _table_exists(conn, name):
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


# ── Header / Footer ───────────────────────────────────────────────────────────
def _on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Header bar
    canvas.setFillColor(COLOR_DARK)
    canvas.rect(0, h - 1.2*cm, w, 1.2*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(1*cm, h - 0.8*cm, "Dwarfium Scope Archive — Statistics Report")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 1*cm, h - 0.8*cm,
                           datetime.now().strftime("%Y-%m-%d %H:%M"))
    # Footer
    canvas.setFillColor(COLOR_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, 0.6*cm, f"Page {doc.page}")
    canvas.restoreState()


# ── Main entry ────────────────────────────────────────────────────────────────
def generate_report(db_path, output_path=None):
    """
    Generate the PDF report.
    Returns the output path.
    Can be called from the NiceGUI app directly.
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(db_path)), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        output_path = os.path.join(reports_dir, f"dwarfium_report_{ts}.pdf")

    conn = connect(db_path)
    styles = build_styles()
    story  = []

    # Cover
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("🔭 Dwarfium Scope Archive", styles["title"]))
    story.append(Paragraph("Statistics Report", styles["subtitle"]))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M')}",
        styles["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY))
    #story.append(Spacer(1, 1*cm))
    story.append(Spacer(1, 1*cm))

    section_summary(conn, styles, story)
    section_drives(conn, styles, story)
    story.append(PageBreak())
    section_top_objects(conn, styles, story, "20")
    section_sessions_error(conn, styles, story)

    conn.close()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        title="Dwarfium Scope Archive — Statistics Report",
        author="Dwarfium Scope Archive",
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    print(f"Report generated: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Dwarfium — Generate PDF statistics report"
    )
    parser.add_argument(
        "--db", default=os.path.join("db", "dwarf_backup.db"),
        help="Path to the SQLite database"
    )
    parser.add_argument(
        "--out", default=None,
        help="Output PDF path (default: db directory)"
    )
    args = parser.parse_args()

    path = generate_report(args.db, args.out)
    print(f"Done: {path}")


if __name__ == "__main__":
    main()