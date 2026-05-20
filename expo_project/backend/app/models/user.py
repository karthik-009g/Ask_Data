import enum


class UserRole(str, enum.Enum):
    """Kept for backward-compat imports; users are now stored in MongoDB."""
    admin = "admin"
    employee = "employee"
