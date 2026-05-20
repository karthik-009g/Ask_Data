import re
from typing import Any

from app.db.mongo import UserDoc


def _clean(value: Any) -> str:
    return str(value or "").strip()


def try_build_direct_answer(user: UserDoc, prompt: str) -> dict[str, Any] | None:
    text = _clean(prompt).lower()
    if not text:
        return None

    if re.search(r"\b(what|which)\b.*\b(my|our)\b.*\b(organisation|organization|org)\b", text):
        org_name = _clean(getattr(user, "organisation", "")) or "unknown"
        answer = f"Your organisation is {org_name}."
        return {
            "intent": "identity.organisation",
            "answer": answer,
            "rows": [{"organisation": org_name}],
            "metadata": {"organisation": org_name},
        }

    if re.search(r"\b(what|which)\b.*\bmy\b.*\b(role|access level)\b", text):
        role_name = _clean(getattr(user, "role", "")) or "unknown"
        answer = f"Your role is {role_name}."
        return {
            "intent": "identity.role",
            "answer": answer,
            "rows": [{"role": role_name}],
            "metadata": {"role": role_name},
        }

    if re.search(r"\b(what|which)\b.*\bmy\b.*\b(email|mail)\b", text):
        email = _clean(getattr(user, "email", "")) or "unknown"
        answer = f"Your email is {email}."
        return {
            "intent": "identity.email",
            "answer": answer,
            "rows": [{"email": email}],
            "metadata": {"email": email},
        }

    return None
