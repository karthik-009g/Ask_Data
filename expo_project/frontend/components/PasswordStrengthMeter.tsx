"use client";

import { PasswordStrength } from "../lib/passwordValidator";

interface PasswordStrengthMeterProps {
  strength: PasswordStrength;
}

const strengthColors = {
  weak: "bg-red-500",
  fair: "bg-yellow-500",
  good: "bg-lime-500",
  strong: "bg-green-600",
};

const strengthTextColors = {
  weak: "text-red-600",
  fair: "text-yellow-600",
  good: "text-lime-600",
  strong: "text-green-700",
};

export function PasswordStrengthMeter({ strength }: PasswordStrengthMeterProps) {
  return (
    <div className="space-y-2">
      {/* Strength Bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <label className="text-xs font-medium text-slate-700">Password Strength</label>
          <span className={`text-xs font-medium ${strengthTextColors[strength.level]}`}>
            {strength.feedback}
          </span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${strengthColors[strength.level]}`}
            style={{ width: `${strength.score}%` }}
          />
        </div>
      </div>

      {/* Requirements Checklist */}
      <div className="bg-slate-50 border border-slate-200 rounded p-3 space-y-2">
        <p className="text-xs font-semibold text-slate-700">Password Requirements:</p>
        {strength.requirements.map((req, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <div
              className={`w-4 h-4 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                req.met ? "bg-green-500" : "bg-slate-300"
              }`}
            >
              {req.met ? "✓" : ""}
            </div>
            <span className={`text-xs ${req.met ? "text-slate-700" : "text-slate-500"}`}>
              {req.name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
