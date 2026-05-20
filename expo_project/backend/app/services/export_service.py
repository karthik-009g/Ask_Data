import io
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def export_csv(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode()


def export_excel(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def export_pdf(rows: list[dict]) -> bytes:
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    y = 750
    for row in rows[:50]:
        c.drawString(40, y, str(row)[:150])
        y -= 14
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    return output.getvalue()
