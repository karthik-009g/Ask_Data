from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PDF = ROOT / "docs" / "Ask-Data-Project-Guide-Detailed.pdf"


def endpoint_rows() -> list[list[str]]:
    return [
        ["Method", "Route", "Purpose", "Role"],
        ["POST", "/api/v1/auth/register", "Create admin account", "Public"],
        ["POST", "/api/v1/auth/login", "Authenticate and issue JWT", "Public"],
        ["POST", "/api/v1/auth/logout", "Logout endpoint", "Admin/Employee"],
        ["GET", "/api/v1/admin/employees", "List org employees", "Admin"],
        ["POST", "/api/v1/admin/employees", "Create employee in same org", "Admin"],
        ["GET", "/api/v1/admin/connections", "List org connections", "Admin"],
        ["POST", "/api/v1/admin/connections", "Create connection", "Admin"],
        ["PUT", "/api/v1/admin/connections/{id}", "Update org connection", "Admin"],
        ["DELETE", "/api/v1/admin/connections/{id}", "Delete org connection", "Admin"],
        ["POST", "/api/v1/admin/permissions", "Assign employee permissions", "Admin"],
        ["GET", "/api/v1/admin/metadata", "Read org schema catalog", "Admin"],
        ["POST", "/api/v1/admin/analyse", "Run admin analysis", "Admin"],
        ["GET", "/api/v1/employee/connections", "List assigned connections", "Employee"],
        ["GET", "/api/v1/employee/schema", "List assigned schema", "Employee"],
        ["POST", "/api/v1/employee/analyse", "Run employee analysis", "Employee"],
        ["POST", "/api/v1/employee/analyse/export/{format}", "Export employee analysis", "Employee"],
    ]


def data_model_rows() -> list[list[str]]:
    return [
        ["Collection", "Key Fields", "Description"],
        ["users", "organisation, email, role", "Admins and employees with organisation scope"],
        ["connections", "connection_id, organisation, db_type", "External datasource registry"],
        ["permissions", "employee_id, connection_id, can_*", "Per-employee access matrix"],
        ["metadata_catalog", "connection_id, table_name, column_name", "Discovered schema catalog"],
        ["query_logs", "employee_id, organisation, prompt", "Execution logs for audit"],
        ["counters", "name, seq", "Sequence IDs for entities"],
    ]


def workflow_diagrams() -> dict[str, str]:
    return {
        "System Architecture": """
[User Browser]
    |
    v
[Next.js Frontend]
    |
    v
[Next.js API Proxy]
    |
    v
[FastAPI Backend]
  |           |            |
  |           |            +--> [Groq/OpenAI/Fallback]
  |           |
  |           +--> [External DBs: MySQL/PostgreSQL/MongoDB]
  |
  +--> [Mongo Atlas Internal Store]
       users/connections/permissions/metadata/query_logs
""",
        "Tenant Isolation": """
[Admin JWT organisation=novexa]
      |
      +--> admin routes filter by organisation=novexa
      +--> sees only novexa employees/connections/metadata/logs

[Admin JWT organisation=annavaram prasadham]
      |
      +--> admin routes filter by organisation=annavaram prasadham
      +--> sees only that org records
""",
        "Connection Onboarding": """
Admin UI -> POST /admin/connections
       -> sanitize payload -> encrypt secrets -> test connection
       -> save with organisation -> refresh metadata
       -> metadata_catalog updated
       -> UI shows connection and schema rows
""",
        "Employee Analysis": """
Employee UI -> POST /employee/analyse
           -> permission check + org scope check
           -> AI/fallback query generation
           -> execute safe reads
           -> rows + overview + analytics returned
           -> optional export csv/excel/pdf
""",
    }


def file_overview_rows() -> list[list[str]]:
    return [
        ["File", "Responsibility"],
        ["backend/app/main.py", "FastAPI boot, middleware, router setup"],
        ["backend/app/api/v1/auth.py", "Login/register/logout and token creation"],
        ["backend/app/api/v1/admin.py", "Admin domain: employees, connections, permissions, metadata, analysis"],
        ["backend/app/api/v1/employee.py", "Employee domain: assigned connections, schema, analysis/export"],
        ["backend/app/services/analysis_service.py", "Cross-source analysis orchestration"],
        ["backend/app/services/query_service.py", "SQL prompt execution with safety checks"],
        ["backend/app/services/connection_service.py", "SQL/Mongo connection construction + validation"],
        ["backend/app/services/metadata_service.py", "Schema extraction into metadata catalog"],
        ["backend/app/core/security.py", "Password hash/verify and JWT encode"],
        ["backend/app/utils/password_validator.py", "Password strength policy on backend"],
        ["frontend/app/page.tsx", "Login page"],
        ["frontend/app/signup-admin/page.tsx", "Admin signup with strength meter"],
        ["frontend/app/admin/page.tsx", "Admin console UI"],
        ["frontend/app/employee/page.tsx", "Employee workspace UI"],
        ["frontend/lib/api.ts", "Frontend API client and error normalization"],
        ["frontend/lib/passwordValidator.ts", "Client-side password strength checks"],
        ["frontend/components/ResultChart.tsx", "Visualization component"],
        ["frontend/components/PasswordStrengthMeter.tsx", "Password strength UI component"],
        ["frontend/app/api/proxy/[...path]/route.ts", "API proxy with backend fallback"],
    ]


def style_table(table: Table) -> None:
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.8),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )


def build() -> None:
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT_PDF), pagesize=A4, leftMargin=34, rightMargin=34, topMargin=32, bottomMargin=32)

    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontSize=21, leading=25)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, leading=19)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, leading=16)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=13)
    mono = ParagraphStyle("Mono", parent=styles["Code"], fontName="Courier", fontSize=8.4, leading=10)

    story = []
    story.append(Paragraph("Ask Data - Detailed Project Guide", title))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body))
    story.append(Spacer(1, 8))
    story.append(Paragraph("This version is a deep technical and operational walkthrough: workflows, API map, data model, tenant isolation, and file-by-file architecture notes.", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("1. Core Workflows", h1))
    workflow_points = [
        "Auth workflow: register -> login -> JWT -> role-based route access.",
        "Admin workflow: create employees, onboard connections, assign permissions.",
        "Metadata workflow: scan external DB schema and store in metadata_catalog.",
        "Employee workflow: query/analyse only assigned and organisation-scoped connections.",
        "Export workflow: convert analysis rows to csv/xlsx/pdf on demand.",
        "Isolation workflow: organisation filter enforced in admin and employee data paths.",
    ]
    for p in workflow_points:
        story.append(Paragraph(f"- {p}", body))

    story.append(Spacer(1, 8))
    story.append(Paragraph("2. Diagrams", h1))
    for name, diagram in workflow_diagrams().items():
        story.append(Paragraph(name, h2))
        story.append(Preformatted(diagram.strip("\n"), mono))
        story.append(Spacer(1, 4))

    story.append(PageBreak())
    story.append(Paragraph("3. API Endpoint Map", h1))
    api_table = Table(endpoint_rows(), colWidths=[42, 168, 215, 78])
    style_table(api_table)
    story.append(api_table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("4. Internal Data Model", h1))
    model_table = Table(data_model_rows(), colWidths=[95, 170, 238])
    style_table(model_table)
    story.append(model_table)

    story.append(PageBreak())
    story.append(Paragraph("5. File-by-File Technical Guide", h1))
    file_table = Table(file_overview_rows(), colWidths=[248, 255])
    style_table(file_table)
    story.append(file_table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("6. Connection and Security Notes", h1))
    notes = [
        "Supports form mode and URL mode for datasource onboarding.",
        "Secrets are encrypted before storage and decrypted only during connection operations.",
        "Password strength validation is enforced in frontend and backend.",
        "JWT now carries organisation claim so UI can display org context.",
        "Legacy records without organisation can be backfilled for visibility after tenant isolation rollout.",
    ]
    for n in notes:
        story.append(Paragraph(f"- {n}", body))

    story.append(Spacer(1, 8))
    story.append(Paragraph("End of detailed guide.", body))

    doc.build(story)
    print(f"Generated: {OUTPUT_PDF}")


if __name__ == "__main__":
    build()
