from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PDF = ROOT / "docs" / "Ask-Data-Project-Guide.pdf"

FILE_EXPLANATIONS = {
    "README.md": "Project overview, architecture summary, setup and runtime instructions.",
    "backend/app/main.py": "FastAPI app bootstrap, middleware setup, health route, and API router wiring.",
    "backend/app/api/v1/router.py": "Aggregates and mounts all versioned API routers.",
    "backend/app/api/v1/auth.py": "Register/login/logout endpoints, organisation-aware auth, password checks.",
    "backend/app/api/v1/admin.py": "Admin features: employee management, data connections, permissions, metadata, analytics, exports.",
    "backend/app/api/v1/employee.py": "Employee-facing routes: permitted connections, schema view, query/analyse/export actions.",
    "backend/app/api/v1/query.py": "Generic NL query and export endpoints with rate limiting.",
    "backend/app/api/v1/debug.py": "Debug utilities and runtime diagnostics endpoints.",
    "backend/app/core/config.py": "Environment settings and configuration defaults.",
    "backend/app/core/security.py": "JWT creation/validation, password hashing and verification helpers.",
    "backend/app/core/dependencies.py": "Auth dependencies and role guards (admin/employee).",
    "backend/app/core/encryption.py": "Encryption/decryption helpers for sensitive stored secrets.",
    "backend/app/db/mongo.py": "Mongo client setup, users collection access, and user lookup helpers.",
    "backend/app/db/system_store.py": "System collections wrappers (connections, metadata, logs, permissions, counters).",
    "backend/app/services/connection_service.py": "Builds SQL/Mongo connection strings, validates and resolves target databases.",
    "backend/app/services/metadata_service.py": "Extracts schema metadata from SQL/Mongo sources into catalog.",
    "backend/app/services/query_service.py": "Query execution orchestration helpers.",
    "backend/app/services/analysis_service.py": "Multi-source analysis orchestration and result shaping.",
    "backend/app/services/ai_service.py": "AI provider selection, SQL/insight generation helpers, fallback logic.",
    "backend/app/services/ai_query_service.py": "Natural language to query pipeline execution.",
    "backend/app/services/export_service.py": "CSV, Excel, and PDF export builders.",
    "backend/app/schemas/auth.py": "Pydantic request/response models for authentication.",
    "backend/app/schemas/connection.py": "Pydantic models for connection payloads and permission assignment.",
    "backend/app/schemas/query.py": "Pydantic models for query and export payloads.",
    "backend/app/schemas/user.py": "Pydantic user output models.",
    "backend/app/models/user.py": "User model definitions used by backend domain.",
    "backend/app/utils/password_validator.py": "Backend password strength rules and detailed validation messaging.",
    "frontend/app/layout.tsx": "Global layout shell, metadata, and root styling wrappers.",
    "frontend/app/page.tsx": "Login page for admin/employee authentication.",
    "frontend/app/signup-admin/page.tsx": "Admin signup page with password strength checker and validation.",
    "frontend/app/admin/page.tsx": "Admin console UI for users, connections, permissions, metadata, and analytics.",
    "frontend/app/employee/page.tsx": "Employee dashboard UI for querying and visual analysis.",
    "frontend/app/api/proxy/[...path]/route.ts": "Next.js API proxy that forwards frontend calls to backend with fallback bases.",
    "frontend/components/ResultChart.tsx": "Chart rendering component for query/analysis results.",
    "frontend/components/PasswordStrengthMeter.tsx": "Reusable strength bar and checklist UI for password requirements.",
    "frontend/lib/api.ts": "HTTP client helper with auth header handling and error normalization.",
    "frontend/lib/passwordValidator.ts": "Frontend password strength scoring and requirement checks.",
    "frontend/tailwind.config.ts": "Tailwind theme/content configuration.",
    "frontend/next-env.d.ts": "Next.js TypeScript ambient type declarations.",
    ".env": "Local environment configuration (secrets, URLs, keys).",
    ".env.example": "Template environment file with required keys and sample values.",
}

WORKFLOWS = [
    (
        "1) Authentication Workflow",
        [
            "Admin registers via /api/v1/auth/register.",
            "Backend normalizes organisation/email, validates password strength, hashes password, stores user.",
            "User logs in via /api/v1/auth/login.",
            "Backend resolves organisation context and returns JWT with role claims.",
            "Frontend stores token and routes user to role-specific dashboard.",
        ],
    ),
    (
        "2) Employee Provisioning Workflow",
        [
            "Admin opens User Management in Admin Console.",
            "Admin enters employee details and temporary password.",
            "Frontend blocks weak passwords with live strength meter.",
            "Backend endpoint /api/v1/admin/employees validates password and persists employee.",
            "Admin can then assign data permissions per connection.",
        ],
    ),
    (
        "3) Connection Onboarding Workflow",
        [
            "Admin creates connection in form mode or URL mode.",
            "Credentials are encrypted before persistence.",
            "Connection test is executed to confirm reachability/authentication.",
            "Metadata refresh extracts schema/table/column information.",
            "Catalog is saved to metadata collection for downstream AI query context.",
        ],
    ),
    (
        "4) Permission Workflow",
        [
            "Admin assigns connection-level permissions to each employee.",
            "Flags include can_read, can_query, can_visualize, can_export.",
            "Employee endpoints filter connections and operations by assigned permissions.",
            "Unauthorized actions are blocked at backend dependency/rule level.",
        ],
    ),
    (
        "5) Query and Analysis Workflow",
        [
            "Employee submits natural-language prompt.",
            "AI query service picks provider (Groq/OpenAI) or fallback mode.",
            "Metadata context guides SQL generation or Mongo strategy.",
            "Only safe read semantics are allowed (SELECT-only for SQL paths).",
            "Results are returned as rows + optional overview + visualization-ready data.",
        ],
    ),
    (
        "6) Export Workflow",
        [
            "User requests export as csv/excel/pdf from query or analysis result.",
            "Export service serializes current rows to selected format.",
            "Frontend receives blob and triggers file download.",
        ],
    ),
]

DIAGRAMS = {
    "High-Level Architecture": """
[Browser: Next.js UI]
       |
       | HTTP (JWT)
       v
[Next.js API Proxy /api/proxy]
       |
       v
[FastAPI Backend]
   |        |         |
   |        |         +--> [AI Provider: Groq/OpenAI]
   |        |
   |        +--> [External Data Sources]
   |                |- MySQL
   |                |- PostgreSQL
   |                '- MongoDB
   |
   +--> [Mongo Atlas Internal Store]
            |- users
            |- connections
            |- permissions
            |- metadata_catalog
            '- query_logs
""",
    "Connection + Metadata Sequence": """
Admin UI -> Admin API (/admin/connections): create connection
Admin API -> encryption: encrypt credentials
Admin API -> system_store: save connection record
Admin API -> connection_service: test connection
Admin API -> metadata_service: refresh metadata
metadata_service -> external DB: inspect schema/collections
metadata_service -> metadata_catalog: save extracted fields
Admin API -> Admin UI: success + refreshed catalog
""",
    "Employee Query Sequence": """
Employee UI -> Employee API (/employee/analyse): prompt + connection_ids
Employee API -> permissions store: validate allowed connections
Employee API -> ai_query_service: build execution plan
ai_query_service -> ai_service: generate SQL/logic (or fallback)
ai_query_service -> query executors: run read queries
ai_query_service -> Employee API: rows + overview + metadata
Employee API -> Employee UI: render table/chart + export options
""",
}


def collect_files() -> list[str]:
    files: list[str] = []
    include_roots = [
        ROOT / "backend" / "app",
        ROOT / "frontend" / "app",
        ROOT / "frontend" / "components",
        ROOT / "frontend" / "lib",
    ]

    for root in include_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".d.ts"}:
                files.append(path.relative_to(ROOT).as_posix())

    for extra in ["README.md", ".env", ".env.example", "frontend/tailwind.config.ts", "frontend/next-env.d.ts"]:
        if (ROOT / extra).exists() and extra not in files:
            files.append(extra)

    return sorted(set(files))


def build_pdf() -> None:
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Ask Data Project Guide",
        author="GitHub Copilot",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=22, leading=26, spaceAfter=12)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1f2937"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, leading=17, textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=14)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=9.5, leading=12)
    mono = ParagraphStyle("Mono", parent=styles["Code"], fontName="Courier", fontSize=8.8, leading=10.8)

    story = []

    story.append(Paragraph("Ask Data - Complete Project Guide", title_style))
    story.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", small))
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "This document explains the full system architecture, connection flow, end-to-end workflows, and a file-by-file technical guide for the current codebase.",
            body,
        )
    )

    story.append(Spacer(1, 12))
    story.append(Paragraph("System Context", h1))
    table_data = [
        ["Layer", "Technology", "Purpose"],
        ["Frontend", "Next.js + React + Tailwind", "Role-based UI (login/signup/admin/employee), chart rendering, API calls"],
        ["Proxy", "Next.js Route Handler", "Forwards frontend requests to backend with fallback targets"],
        ["Backend", "FastAPI", "Auth, RBAC, connection mgmt, metadata, query, export"],
        ["Internal Store", "MongoDB Atlas", "Users, connections, permissions, metadata catalog, logs"],
        ["External Sources", "MySQL/PostgreSQL/MongoDB", "Business data queried by users"],
        ["AI Providers", "Groq/OpenAI/Fallback", "NL to query + overview generation"],
    ]
    table = Table(table_data, colWidths=[85, 145, 260])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    story.append(Spacer(1, 14))
    story.append(Paragraph("Architecture Diagrams", h1))
    for title, diagram in DIAGRAMS.items():
        story.append(Paragraph(title, h2))
        story.append(Preformatted(diagram.strip("\n"), mono))
        story.append(Spacer(1, 8))

    story.append(PageBreak())
    story.append(Paragraph("Workflow Explanations", h1))
    for workflow_title, steps in WORKFLOWS:
        story.append(Paragraph(workflow_title, h2))
        for step in steps:
            story.append(Paragraph(f"- {step}", body))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Connection Modes and Data Paths", h2))
    connection_notes = [
        "Form mode: admin provides host/port/username/password/database_name fields.",
        "URL mode: admin provides complete connection_url; parser preserves database path and query options.",
        "Secrets are encrypted before persistence and decrypted only at runtime for test/query operations.",
        "Metadata refresh normalizes schema info into metadata_catalog used by AI and schema UI.",
        "Permission checks gate which connections an employee can read/query/visualize/export.",
    ]
    for item in connection_notes:
        story.append(Paragraph(f"- {item}", body))

    story.append(PageBreak())
    story.append(Paragraph("File-by-File Explanation", h1))
    story.append(Paragraph("This section lists key files in the current repository and their responsibilities.", body))
    story.append(Spacer(1, 6))

    for file_path in collect_files():
        explanation = FILE_EXPLANATIONS.get(file_path, "Code module used by this project. Review source for implementation specifics.")
        story.append(Paragraph(f"<b>{file_path}</b>", small))
        story.append(Paragraph(explanation, body))
        story.append(Spacer(1, 4))

    story.append(PageBreak())
    story.append(Paragraph("How To Read This Project Quickly", h1))
    quick_start = [
        "1. Start with frontend/app/page.tsx and frontend/app/signup-admin/page.tsx for user entry points.",
        "2. Inspect backend/app/api/v1/auth.py and backend/app/core/security.py for auth mechanics.",
        "3. Move to frontend/app/admin/page.tsx and backend/app/api/v1/admin.py for core admin workflows.",
        "4. Read backend/app/services/connection_service.py and metadata_service.py for data-source onboarding.",
        "5. Read frontend/app/employee/page.tsx plus backend employee/query/analysis services for analytics flow.",
        "6. Review frontend/lib/api.ts and proxy route for request routing and fallback behavior.",
        "7. Finally, review password validators in frontend/lib/passwordValidator.ts and backend/app/utils/password_validator.py.",
    ]
    for line in quick_start:
        story.append(Paragraph(line, body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("End of Document", small))

    doc.build(story)


if __name__ == "__main__":
    build_pdf()
    print(f"Generated: {OUTPUT_PDF}")
