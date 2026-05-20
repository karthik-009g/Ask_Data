import re


class PasswordValidator:
    """Validates password strength based on configurable requirements."""
    
    MIN_LENGTH = 8
    REQUIRES_UPPERCASE = True
    REQUIRES_DIGIT = True
    REQUIRES_SPECIAL = True
    
    @staticmethod
    def validate(password: str) -> tuple[bool, list[str]]:
        """
        Validate password strength.
        
        Returns:
            (is_valid, missing_requirements)
            - is_valid: True if password meets all requirements
            - missing_requirements: List of unmet requirements
        """
        missing = []
        
        if len(password) < PasswordValidator.MIN_LENGTH:
            missing.append(f"At least {PasswordValidator.MIN_LENGTH} characters")
        
        if PasswordValidator.REQUIRES_UPPERCASE and not re.search(r'[A-Z]', password):
            missing.append("At least 1 uppercase letter (A-Z)")
        
        if PasswordValidator.REQUIRES_DIGIT and not re.search(r'\d', password):
            missing.append("At least 1 number (0-9)")
        
        if PasswordValidator.REQUIRES_SPECIAL and not re.search(
            r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password
        ):
            missing.append("At least 1 special character (!@#$%^&*)")
        
        return len(missing) == 0, missing
    
    @staticmethod
    def get_error_message(missing: list[str]) -> str:
        """Generate user-friendly error message from missing requirements."""
        if not missing:
            return "Password meets strength requirements"
        return "Password does not meet requirements: " + ", ".join(missing)
