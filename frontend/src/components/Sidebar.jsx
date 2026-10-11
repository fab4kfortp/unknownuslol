import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import LanguageSwitcher from "./LanguageSwitcher.jsx";

const MOBILE_TABS = ["dashboard", "transactions", "priority", "calendar"];

function Brand({ compact = false }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <img src="/logo-icon.png" alt="SpendShield logo" className={`${compact ? "h-8 w-8" : "h-11 w-11"} shrink-0 object-contain`} />
      <span className={`${compact ? "text-lg" : "text-[22px]"} whitespace-nowrap font-display font-extrabold tracking-tight leading-none`}>
        <span className="text-navy">Spend</span>
        <span className="bg-gradient-to-r from-[#1D604C] to-[#3FA873] bg-clip-text text-transparent">Shield</span>
      </span>
    </div>
  );
}

function Sidebar({ tabs, activeTab, onSelect, onSwitchMode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const primaryTabs = tabs.filter((tab) => MOBILE_TABS.includes(tab.id));
  const moreTabs = tabs.filter((tab) => !MOBILE_TABS.includes(tab.id));

  useEffect(() => setMoreOpen(false), [activeTab]);
  useEffect(() => {
    if (!moreOpen) return undefined;
    const closeOnEscape = (event) => event.key === "Escape" && setMoreOpen(false);
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [moreOpen]);

  const renderTab = (tab, mobile = false) => {
    const Icon = tab.icon;
    const isActive = tab.id === activeTab;
    return (
      <button
        key={tab.id}
        type="button"
        onClick={() => onSelect(tab.id)}
        aria-current={isActive ? "page" : undefined}
        className={mobile
          ? `flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[10px] font-semibold ${isActive ? "text-emerald-800" : "text-slate-500"}`
          : `w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-all ${isActive ? "bg-gradient-to-r from-emerald-500/20 to-teal-500/10 text-navy font-semibold shadow-sm ring-1 ring-emerald-600/15" : "text-slate-500 hover:bg-emerald-500/10 hover:text-navy"}`}
      >
        <Icon size={mobile ? 19 : 17} className={isActive ? "text-accent" : "text-slate-400"} />
        <span className={mobile ? "max-w-full truncate" : ""}>{mobile ? tab.label === "Transactions" ? "Activity" : tab.label === "Priority List" ? "Priority" : tab.label === "Bill Calendar" ? "Bills" : "Home" : tab.label}</span>
      </button>
    );
  };

  return (
    <>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-cardborder bg-white/70 backdrop-blur-xl md:flex">
        <div className="space-y-4 px-5 py-6"><Brand /><LanguageSwitcher /></div>
        <nav aria-label="Main navigation" className="flex-1 space-y-1 overflow-y-auto px-3">
          {tabs.map((tab) => renderTab(tab))}
        </nav>
        <div className="border-t border-cardborder px-6 py-5">
          <p className="text-xs font-semibold text-navy/80">Simulate the consequences.</p>
          <p className="text-xs font-semibold text-accent">Then decide.</p>
          {onSwitchMode && <button type="button" onClick={onSwitchMode} className="mt-3 w-full rounded-xl border border-emerald-600/20 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-900 transition-all hover:bg-emerald-500/20">⚡ Switch Data / Demo</button>}
        </div>
      </aside>

      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-cardborder bg-white/95 px-4 shadow-sm backdrop-blur md:hidden">
        <Brand compact />
        <div className="flex min-w-0 items-center gap-2"><span className="max-w-[35vw] truncate text-right text-xs font-semibold text-slate-500">{tabs.find((tab) => tab.id === activeTab)?.label}</span><LanguageSwitcher compact /></div>
      </header>

      {moreOpen && <button type="button" aria-label="Close navigation menu" className="fixed inset-0 z-40 bg-slate-950/30 md:hidden" onClick={() => setMoreOpen(false)} />}
      {moreOpen && (
        <section role="dialog" aria-label="More sections" className="fixed inset-x-3 bottom-[5.2rem] z-50 max-h-[70dvh] overflow-y-auto rounded-2xl border border-cardborder bg-white p-4 shadow-2xl md:hidden">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-navy">All sections</h2>
            <button type="button" aria-label="Close menu" onClick={() => setMoreOpen(false)} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X size={18} /></button>
          </div>
          <nav aria-label="More sections" className="grid grid-cols-2 gap-2">
            {moreTabs.map((tab) => renderTab(tab))}
          </nav>
          {onSwitchMode && <button type="button" onClick={() => { setMoreOpen(false); onSwitchMode(); }} className="mt-3 w-full rounded-xl bg-emerald-50 px-3 py-3 text-sm font-semibold text-emerald-900">⚡ Switch Data / Demo</button>}
        </section>
      )}
      <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-cardborder bg-white/95 px-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] pt-1 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur md:hidden">
        {primaryTabs.map((tab) => renderTab(tab, true))}
        <button type="button" aria-expanded={moreOpen} onClick={() => setMoreOpen((open) => !open)} className={`flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[10px] font-semibold ${moreOpen || moreTabs.some((tab) => tab.id === activeTab) ? "text-emerald-800" : "text-slate-500"}`}>
          {moreOpen ? <X size={19} /> : <Menu size={19} />}
          <span>More</span>
        </button>
      </nav>
    </>
  );
}

export default Sidebar;
