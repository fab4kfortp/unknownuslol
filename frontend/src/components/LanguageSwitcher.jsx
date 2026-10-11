import { useEffect, useState } from "react";
import { getLanguage, setLanguage } from "../language";

export default function LanguageSwitcher({ compact = false }) {
  const [language, setCurrentLanguage] = useState(getLanguage);

  useEffect(() => {
    const update = (event) => setCurrentLanguage(event.detail || getLanguage());
    window.addEventListener("spendshield-language-change", update);
    return () => window.removeEventListener("spendshield-language-change", update);
  }, []);

  if (compact) {
    return (
      <label className="sr-only">
        Language
        <select aria-label="Language" value={language} onChange={(event) => setLanguage(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-600">
          <option value="en">English</option>
          <option value="hi">हिन्दी</option>
        </select>
      </label>
    );
  }

  return (
    <div role="group" aria-label="Language" className="inline-flex shrink-0 rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-semibold">
      <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")} className={`rounded-md px-2.5 py-1.5 transition ${language === "en" ? "bg-emerald-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}>English</button>
      <button type="button" aria-pressed={language === "hi"} onClick={() => setLanguage("hi")} className={`rounded-md px-2.5 py-1.5 transition ${language === "hi" ? "bg-emerald-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}>हिन्दी</button>
    </div>
  );
}
