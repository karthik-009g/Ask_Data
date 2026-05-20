from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Ask-Data-Agentic-Project-Guide.pdf"


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def build_pdf() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=34,
        rightMargin=34,
        topMargin=32,
        bottomMargin=32,
        title="Ask Data Agentic Guide",
        author="GitHub Copilot",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontSize=21, leading=25)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, leading=19)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, leading=15)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=13)
    mono = ParagraphStyle("Mono", parent=styles["Code"], fontName="Courier", fontSize=8.5, leading=10)

    story = []
    story.append(Paragraph("Ask Data - Complete Agentic AI Project Guide", title))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body))
    story.append(Spacer(1, 8))
    story.append(Paragraph("This report explains the full agentic setup in your project, what each agent does for users, what each agent does in the backend pipeline, and how modules are separated in UI.", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("1. Is This Now an Agentic AI Project?", h1))
    story.append(
        Paragraph(
            "Yes. This is now a bounded multi-agent analytics system. It does not use one uncontrolled mega-agent. "
            "Instead, the flow is split into smaller agents with clear responsibilities: intent routing, planning, governance checks, generation, repair, execution, insight, and trend watch.",
            body,
        )
    )
    story.append(Paragraph("Current maturity: practical production-oriented agentic foundation with read-only governance and traceable execution.", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("2. Agentic Architecture in One View", h1))
    seq = """
User Prompt
 -> Intent Router Agent
 -> (Direct Answer OR Clarification OR Data Query Path)
 -> Query Planner Agent
 -> Governance Policy Agent
 -> SQL Generation Agent
 -> SQL Repair Agent (if needed)
 -> Multi-source Execution Agent
 -> Business Insight Agent
 -> Trend Watch Agent
 -> Agentic Trace + UI Panels
"""
    story.append(Preformatted(seq.strip("\n"), mono))

    story.append(Spacer(1, 10))
    story.append(Paragraph("3. What Each Agent Does", h1))
    rows = [
        ["Agent", "Role In Project", "What User Gets", "Guardrail"],
        [
            "Intent Router Agent",
            "Classifies prompt: direct answer, metadata question, or query",
            "Fast answer for profile/context/schema questions without unnecessary SQL",
            "Only routes to SQL path when required",
        ],
        [
            "Query Planner Agent",
            "Selects best connection/tables and confidence",
            "Better source targeting and fewer wrong queries",
            "Can trigger clarification when confidence is low",
        ],
        [
            "SQL Generation Agent",
            "Builds safe query from intent + schema context",
            "Natural-language to data output",
            "Read-only constraints before execution",
        ],
        [
            "SQL Repair Agent",
            "Retries failed SQL using error-aware hints",
            "Higher success on first-run failures",
            "Bounded retry count",
        ],
        [
            "Governance Policy Agent",
            "Enforces RBAC, row caps, query/export limits",
            "Enterprise-safe behavior and permission compliance",
            "Hard block on violations",
        ],
        [
            "Execution Agent",
            "Runs across allowed SQL/Mongo data sources",
            "Unified result set across selected sources",
            "Connection-level permission checks",
        ],
        [
            "Business Insight Agent",
            "Converts raw rows to business narrative and metrics",
            "Readable summary instead of only raw tables",
            "Suppresses identifier-like noise fields",
        ],
        [
            "Trend Watch Agent",
            "Computes week-over-week change and alert signals",
            "Proactive trend/anomaly detection",
            "Only emits trend when time axis is valid",
        ],
    ]
    t = Table(rows, colWidths=[95, 150, 140, 115])
    t.setStyle(_table_style())
    story.append(t)

    story.append(Spacer(1, 10))
    story.append(Paragraph("4. What Users Experience", h1))
    for item in [
        "Natural-language answers for organisation/profile/context questions.",
        "Schema/table/column discovery answers without forcing SQL every time.",
        "Business summary in plain language after data execution.",
        "Trend Watch outputs for week-over-week movement.",
        "Proactive alerts for anomalies such as spikes, drops, or null patterns.",
        "Clarification prompts when the request is ambiguous.",
    ]:
        story.append(Paragraph(f"- {item}", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("5. UI Module Separation (Latest)", h1))
    for item in [
        "Natural Bot is now a standalone top-level module.",
        "Analytics Studio remains a separate module for generated queries, results, charts, and trace inspection.",
        "Data Sources and Schema modules stay independent for governance and discoverability.",
        "This separation prevents mixing chat intent collection with studio analysis review.",
    ]:
        story.append(Paragraph(f"- {item}", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("6. Why Agentic Panels Can Look Empty", h1))
    for item in [
        "Analysis request failed (auth, permission, backend down, bad query).",
        "Prompt is ambiguous and agent asks for clarification instead of execution.",
        "No rows returned, so trace has limited sections.",
        "Backend not running or blocked by task startup command issue.",
    ]:
        story.append(Paragraph(f"- {item}", body))

    story.append(Paragraph("The UI displays current error details when trace data is missing, so users can identify the cause quickly.", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Role-Based Agentic Behavior", h1))
    role_table = Table(
        [
            ["Role", "Primary Agentic Value"],
            ["Employee", "Ask natural questions safely within assigned permissions; receive trends and summaries."],
            ["Admin", "Manage data/permissions and run agentic analytics with governance visibility."],
            ["Super Admin", "Cross-organisation governance and platform-level control (foundation ready)."],
        ],
        colWidths=[110, 365],
    )
    role_table.setStyle(_table_style())
    story.append(role_table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("8. Runtime Note", h1))
    story.append(
        Paragraph(
            "In this workspace, the predefined backend task command is misquoted around a path with spaces ('c:\\my projects...') and fails with 'c:\\my is not recognized'. "
            "Backend endpoint can still be up if another process already occupies port 8000.",
            body,
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("9. Next Agents to Add", h1))
    for item in [
        "Connection Triage Agent (super admin): classify auth/network/db/schema failures with confidence and evidence.",
        "Data Quality Watchdog Agent: scheduled checks for freshness/null spikes/row-count drift with suppression windows.",
        "Permission Recommendation Agent (admin): least-privilege suggestions requiring human approval.",
        "Report Builder Agent: convert goal to scheduled report with preview + approval.",
    ]:
        story.append(Paragraph(f"- {item}", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("10. Agentic Sequence (Current)", h2))
    seq2 = """
Prompt -> Planner score -> (Clarification if low confidence)
      -> Policy & RBAC checks -> SQL generation
      -> Repair loop (max retries) -> Execution
      -> Business analytics cleanup -> Trend snapshot
      -> Proactive alerts + human brief -> UI trace
"""
    story.append(Preformatted(seq2.strip("\n"), mono))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Conclusion", h2))
    story.append(Paragraph("Your project is now agentic in a practical, enterprise-safe way: separate agents, clear guardrails, transparent traces, and role-aware user outcomes.", body))

    doc.build(story)
    return OUTPUT


if __name__ == "__main__":
    out = build_pdf()
    print(f"Generated: {out}")
