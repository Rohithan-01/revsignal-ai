"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  FileUp,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRevenueData } from "@/components/data-provider";

const navigation = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Deals", href: "/deals", icon: Target },
  { label: "Recommendations", href: "/recommendations", icon: Sparkles },
  { label: "Import data", href: "/import", icon: FileUp },
];

function titleForPath(path: string): string {
  if (path === "/") return "Overview";
  if (path.startsWith("/deals/")) return "Deal intelligence";
  return navigation.find((item) => item.href === path)?.label || "RevSignal";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchRef = useRef<HTMLInputElement>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { source, refresh, loading, deals } = useRevenueData();
  const searchResults = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return [];
    return deals
      .filter((deal) => deal.deal_id.toLowerCase().includes(query) || deal.account_name.toLowerCase().includes(query))
      .slice(0, 5);
  }, [deals, search]);

  useEffect(() => {
    function onShortcut(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") setSearchOpen(false);
    if (event.key === "Enter" && searchResults[0]) {
      router.push(`/deals/${encodeURIComponent(searchResults[0].deal_id)}`);
      setSearch("");
      setSearchOpen(false);
    }
  }

  const sidebar = (
    <div className="sidebar-inner">
      <Link className="brand" href="/" onClick={() => setMobileOpen(false)}>
        <span className="brand-mark"><Activity size={19} strokeWidth={2.5} /></span>
        <span>revsignal<span className="brand-period">.</span></span>
      </Link>
      <div className="workspace-switch">
        <div className="workspace-avatar">R</div>
        <div className="workspace-copy"><strong>RevSignal workspace</strong><span>Local development</span></div>
      </div>
      <div className="nav-section-label">WORKSPACE</div>
      <nav className="main-nav" aria-label="Main navigation">
        {navigation.map(({ label, href, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname === href || (href === "/deals" && pathname.startsWith("/deals/"));
          return (
            <Link
              key={href}
              href={href}
              className={`nav-link${active ? " active" : ""}`}
              aria-current={active ? "page" : undefined}
              onClick={() => setMobileOpen(false)}
            >
              {active && <motion.span className="nav-active-indicator" layoutId="active-navigation" transition={{ type: "spring", stiffness: 430, damping: 34 }} />}
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
              {label === "Deals" && deals.length > 0 && <span className="nav-count">{deals.length}</span>}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note">
          <div className="sidebar-note-icon"><BarChart3 size={16} /></div>
          <strong>Revenue clarity, daily.</strong>
          <p>Know where to focus before the quarter gets away.</p>
          <Link href="/deals">Explore your pipeline <ArrowUpRight size={13} /></Link>
        </div>
        <div className="user-row">
          <div className="user-avatar">RS</div>
          <div className="workspace-copy"><strong>Revenue team</strong><span>Local workspace</span></div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="app-frame">
      <aside className="desktop-sidebar">{sidebar}</aside>
      {mobileOpen && (
        <div className="mobile-sidebar-wrap">
          <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
          <aside className="mobile-sidebar">
            <button className="mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={18} /></button>
            {sidebar}
          </aside>
        </div>
      )}
      <main className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu-button icon-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></button>
            <span className="topbar-section">Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <span className="topbar-current">{titleForPath(pathname)}</span>
          </div>
          <div className="topbar-search-wrap">
            <div className={`topbar-search${searchOpen ? " topbar-search-open" : ""}`}>
              <Search size={15} />
              <input
                ref={searchRef}
                aria-label="Search deals and accounts"
                placeholder="Search deals…"
                value={search}
                onFocus={() => setSearchOpen(true)}
                onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
                onChange={(event) => { setSearch(event.target.value); setSearchOpen(true); }}
                onKeyDown={handleSearchKeyDown}
              />
              <kbd>Ctrl K</kbd>
            </div>
            {searchOpen && search.trim() && (
              <div className="search-results" role="group" aria-label="Deal search results">
                {searchResults.length ? searchResults.map((deal) => (
                  <Link
                    key={deal.deal_id}
                    href={`/deals/${encodeURIComponent(deal.deal_id)}`}
                    className="search-result"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => { setSearch(""); setSearchOpen(false); }}
                  >
                    <span className="search-result-initial">{deal.account_name.slice(0, 1)}</span>
                    <span><strong>{deal.account_name}</strong><small>{deal.deal_id} · {deal.stage}</small></span>
                    <span className={`search-risk search-risk-${deal.risk_level.toLowerCase()}`}>{deal.risk_level.toLowerCase()}</span>
                  </Link>
                )) : <div className="search-no-results">No deals found for “{search}”.</div>}
              </div>
            )}
          </div>
          <div className="topbar-right">
            <div className={`source-indicator ${source === "demo" ? "source-demo" : ""}`}>
              <span className="source-dot" />
              {source === "live" ? "Live data" : "Demo data"}
            </div>
            <button className="icon-button refresh-button" onClick={() => void refresh()} disabled={loading} aria-label="Refresh data" title="Refresh data">
              <RefreshCw size={16} className={loading ? "spin" : ""} />
            </button>
            <div className="topbar-divider" />
            <div className="topbar-user"><span className="topbar-user-avatar">R</span><span className="topbar-user-label">Local</span></div>
          </div>
        </header>
        {source === "demo" && (
          <div className="demo-banner">
            <Sparkles size={14} />
            <span><strong>Demo mode</strong> · Showing illustrative sample deals. Start the API to see your imported CRM data.</span>
          </div>
        )}
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
