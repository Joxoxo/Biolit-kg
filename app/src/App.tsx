import { useState } from "react";
import { MessageCircle, Microscope, Home, Menu, X, ShieldCheck } from "lucide-react";
import HomePage from "@/pages/Home";
import DrugProfilePage from "@/pages/DrugProfilePage";
import QaPage from "@/pages/QaPage";
import ExtractPage from "@/pages/ExtractPage";

type TabId = "home" | "profile" | "qa" | "extract";

const TABS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "home", label: "概览", icon: Home },
  { id: "profile", label: "药物安全档案", icon: ShieldCheck },
  { id: "qa", label: "智能问答", icon: MessageCircle },
  { id: "extract", label: "在线抽取", icon: Microscope },
];

export default function App() {
  const [tab, setTab] = useState<TabId>("home");
  const [mobileOpen, setMobileOpen] = useState(false);

  const navigate = (id: TabId) => {
    setTab(id);
    setMobileOpen(false);
  };

  return (
    <div className="h-[100dvh] overflow-hidden bg-white text-[#0a0a0a] flex flex-col">
      <header className="sticky top-0 z-40 bg-white pv-border-b">
        <div className="flex items-stretch h-16">
          <div className="flex items-center gap-3 px-5 pv-border-r shrink-0">
            <span className="block w-5 h-5 bg-[var(--pv-accent)]" aria-hidden="true" />
            <div className="leading-none">
              <div className="mono font-bold text-[14px] tracking-tight">BIOLIT-KG</div>
              <div className="text-[12px] text-black/55 mt-1">药物警戒知识图谱与智能问答</div>
            </div>
          </div>

          <nav className="hidden md:flex items-stretch" role="tablist" aria-label="主导航">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => navigate(t.id)}
                  className={`flex items-center gap-2 px-6 text-[13.5px] font-bold transition-colors cursor-pointer border-b-2 ${
                    active
                      ? "text-[var(--pv-accent)] border-[var(--pv-accent)]"
                      : "text-black/55 border-transparent hover:text-black hover:border-black/10"
                  }`}
                >
                  <Icon size={15} />
                  {t.label}
                </button>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden ml-auto px-4 flex items-center gap-2 text-[12px] font-bold"
            aria-expanded={mobileOpen}
            aria-controls="mobile-menu"
            aria-label="菜单"
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
            <span className="uppercase tracking-wider">Menu</span>
          </button>
        </div>

        {mobileOpen && (
          <nav id="mobile-menu" className="md:hidden pv-border-t bg-white" role="menu">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="menuitem"
                  onClick={() => navigate(t.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-[13px] font-bold border-b border-black/10 ${
                    active ? "text-[var(--pv-accent)] bg-[var(--pv-accent-soft)]" : "text-black/70"
                  }`}
                >
                  <Icon size={16} />
                  {t.label}
                </button>
              );
            })}
          </nav>
        )}
      </header>

      <main className="flex-1 min-h-0 flex flex-col">
        {tab === "home" && <HomePage onNavigate={(id) => setTab(id as TabId)} />}
        {tab === "profile" && <DrugProfilePage />}
        {tab === "qa" && <QaPage />}
        {tab === "extract" && <ExtractPage />}
      </main>

      <footer className="pv-border-t px-6 py-4 flex flex-wrap gap-x-6 gap-y-1 items-center justify-between">
        <p className="text-[12px] text-black/50">
          数据来源：PubMed 摘要级人工标注与自动抽取 · 结论仅反映文献报告，不构成临床建议
        </p>
        <p className="pv-label">BIOLIT-KG · {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
}
