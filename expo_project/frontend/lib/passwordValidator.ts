export interface PasswordRequirement {
  name: string;
  met: boolean;
  regex: RegExp;
}

export interface PasswordStrength {
  score: number;
  level: "weak" | "fair" | "good" | "strong";
  requirements: PasswordRequirement[];
  feedback: string;
}

const requirements: PasswordRequirement[] = [
  {
    name: "At least 8 characters",
    met: false,
    regex: /.{8,}/,
  },
  {
    name: "At least 1 uppercase letter (A-Z)",
    met: false,
    regex: /[A-Z]/,
  },
  {
    name: "At least 1 number (0-9)",
    met: false,
    regex: /\d/,
  },
  {
    name: "At least 1 special character (!@#$%^&*)",
    met: false,
    regex: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/,
  },
];

export function validatePassword(password: string): PasswordStrength {
  const checked = requirements.map((req) => ({
    ...req,
    met: req.regex.test(password),
  }));

  const metCount = checked.filter((req) => req.met).length;
  
  let level: "weak" | "fair" | "good" | "strong" = "weak";
  let feedback = "Password is too weak";
  
  if (password.length === 0) {
    level = "weak";
    feedback = "Enter a password";
  } else if (metCount === 1 || metCount === 2) {
    level = "weak";
    feedback = "Password is weak";
  } else if (metCount === 3) {
    level = "fair";
    feedback = "Password is fair";
  } else if (metCount === 4) {
    level = "good";
    feedback = "Password is good";
  }

  // Bonus points for length
  if (password.length >= 12 && metCount === 4) {
    level = "strong";
    feedback = "Password is strong";
  }

  return {
    score: (metCount / requirements.length) * 100,
    level,
    requirements: checked,
    feedback,
  };
}

export function isPasswordStrong(password: string): boolean {
  const strength = validatePassword(password);
  return strength.level === "good" || strength.level === "strong";
}
