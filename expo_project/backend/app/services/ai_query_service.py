from app.db.mongo import UserDoc
from app.services.query_service import execute_prompt


def run_nl_query(employee: UserDoc, question: str) -> dict:
    generated_sql, rows, execution_time = execute_prompt(employee, question)
    columns = list(rows[0].keys()) if rows else []
    return {
        "generated_sql": generated_sql,
        "columns": columns,
        "rows": rows,
        "execution_time": execution_time,
    }
