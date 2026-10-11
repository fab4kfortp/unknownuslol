import { useState } from "react";
import { ArrowRight, Eye, EyeOff, LockKeyhole, ShieldCheck } from "lucide-react";
import { loginAccount, registerAccount } from "../api";
import LanguageSwitcher from "./LanguageSwitcher.jsx";

export default function LoginScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const account = mode === "login"
        ? await loginAccount({ email, password })
        : await registerAccount({ email, password });
      onAuthenticated(account);
    } catch (err) {
      setError(err.message || "Could not sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative min-h-screen app-bg flex items-center justify-center px-4 py-16 sm:py-10">
      <div className="absolute right-4 top-4"><LanguageSwitcher /></div>
      <section className="w-full max-w-md rounded-[2rem] bg-white p-8 shadow-2xl shadow-emerald-950/10 sm:p-10">
        <div className="mb-8 text-center">
          <img src="/logo-icon.png" alt="SpendShield" className="mx-auto mb-4 h-14 w-14 object-contain" />
          <p className="text-sm font-bold tracking-[0.2em] text-emerald-700">SPENDSHIELD</p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-navy">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Sign in to access your financial workspace.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-5">
          <label className="block text-sm font-semibold text-slate-700">
            Email address
            <input
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
              placeholder="you@example.com"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            Password
            <span className="relative mt-2 block">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={8}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 pr-12 outline-none transition focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                placeholder="At least 8 characters"
              />
              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-3 text-slate-400 hover:text-slate-700"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          </label>

          {error && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#10a66e] px-5 py-3.5 font-bold text-white shadow-lg shadow-emerald-900/15 transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-60"
          >
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            {!busy && <ArrowRight size={18} />}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          {mode === "login" ? "New to SpendShield?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
            className="font-bold text-emerald-700 hover:text-emerald-900"
          >
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>

        <div className="mt-8 flex items-start gap-3 rounded-2xl bg-emerald-50 p-4 text-xs leading-5 text-emerald-900">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-emerald-700" />
          <span><strong>Protected workspace.</strong> Your API access is tied to your account. Use a unique password.</span>
        </div>
        <div className="mt-5 flex items-center justify-center gap-2 text-[11px] text-slate-400">
          <LockKeyhole size={13} /> Account data stays in your SpendShield session.
        </div>
      </section>
    </main>
  );
}
