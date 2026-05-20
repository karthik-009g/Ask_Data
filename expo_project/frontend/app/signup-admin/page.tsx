"use client";

import Link from "next/link";
import Image from "next/image";

export default function AdminSignupPage() {
  return (
    <main className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="bg-white border border-slate-200 p-7 rounded-2xl shadow-sm w-full max-w-md space-y-4">
        <div className="space-y-3">
          <Image src="/expo_logo-removebg-preview.png" alt="Ask Data" width={240} height={240} priority className="h-auto w-[200px] sm:w-[220px]" />
          <h1 className="text-2xl font-bold text-slate-900">Admin Self-Signup Disabled</h1>
          <p className="text-sm text-slate-600 mt-1">For enterprise governance, admin accounts are provisioned only by super admins.</p>
        </div>
        <p className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">
          Contact your platform super admin to create an admin account for your organisation.
        </p>
        <div className="text-sm text-center">
          <Link href="/" className="text-blue-700 hover:underline">Back to Login</Link>
        </div>
      </div>
    </main>
  );
}
