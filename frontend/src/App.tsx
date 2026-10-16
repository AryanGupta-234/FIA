import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, Bell, ArrowUpRight, Bookmark, BookmarkCheck,
  Check, ChevronRight, CircleDollarSign, Clock3, Compass, Crown, ExternalLink,
  Eye, Filter, Heart, History, LayoutDashboard, LoaderCircle, LockKeyhole,
  Menu, PackageSearch, Plus, Radar, RefreshCw, Search, Settings2, ShieldCheck,
  Shirt, Sparkles, SlidersHorizontal, Sparkle, Star, Tag, TrendingDown,
  WandSparkles, Watch, X, Zap,
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

type Product = {
  id: number;
  title: string;
  canonical_url: string;
  description?: string | null;
  brand?: string | null;
  category?: string | null;
  product_type?: string | null;
  colour?: string | null;
  material?: string | null;
  fit?: string | null;
  size_label?: string | null;
  gender?: string | null;
  sku?: string | null;
  gtin?: string | null;
  image_url?: string | null;
  image_source?: string | null;
  price?: number | null;
  original_price?: number | null;
  discount_percent?: number | null;
  currency?: string;
  availability?: string | null;
  seller_name?: string | null;
  offer_label?: string | null;
  offer_valid_until?: string | null;
  retailer_domain: string;
  retailer_name?: string | null;
  source: string;
  last_seen?: string | null;
  price_checked_at?: string | null;
  price_freshness?: "fresh" | "stale" | "unknown";
  price_age_hours?: number | null;
  relevance_score?: number;
  trust_score?: number;
  trust_label?: string;
  reasons?: string[];
  is_saved?: boolean;
};

type ResearchJob = {
  job_id: string;
  status: string;
  query: string;
  result_count: number;
  error?: string | null;
  products: Product[];
};

type HistoryItem = {
  job_id: string;
  query: string;
  status: string;
  result_count: number;
  created_at?: string;
};

type SavedSearch = {
  id: number;
  query: string;
  budget_max?: number | null;
  category?: string | null;
  active: boolean;
  last_run_at?: string | null;
  next_refresh_at?: string | null;
};

type Stats = {
  products: number;
  research_jobs: number;
  completed_jobs: number;
  offers: number;
  saved_products: number;
  saved_searches: number;
  price_alerts_unread: number;
};

type PriceAlert = {
  id: number;
  product_id: number;
  title: string;
  image_url?: string | null;
  canonical_url: string;
  previous_price: number;
  current_price: number;
  currency: string;
  drop_percent: number;
  created_at?: string | null;
  read_at?: string | null;
};

type Health = {
  status: string;
  provider: string;
  live_discovery: boolean;
  automatic_offer_refresh: boolean;
  refresh_interval_minutes: number;
  price_stale_after_hours: number;
  price_alert_cooldown_hours: number;
  default_price_alert_threshold_percent: number;
};

type Preferences = {
  preferred_categories: string[];
  preferred_brands: string[];
  preferred_colours: string[];
  sizes: Record<string, string>;
  style_notes: string;
  budget_default: number | null;
  price_alert_threshold_percent: number;
};

type View = "overview" | "discover" | "offers" | "alerts" | "saved" | "history" | "profile";

const EMPTY_STATS: Stats = {
  products: 0, research_jobs: 0, completed_jobs: 0, offers: 0, saved_products: 0, saved_searches: 0, price_alerts_unread: 0,
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    let message = "Request failed (" + response.status + ")";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = (await response.text()).slice(0, 240) || message;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function money(value?: number | null, currency = "INR") {
  if (value === null || value === undefined) return "Price unavailable";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency", currency, maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return "₹" + Math.round(value).toLocaleString("en-IN");
  }
}

function relativeTime(value?: string | null) {
  if (!value) return "Not refreshed yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";
  const mins = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (mins < 1) return "Just now";
  if (mins < 60) return mins + " min ago";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + " hr ago";
  return Math.floor(hrs / 24) + " days ago";
}

function Logo({ compact = false }: { compact?: boolean }) {
  return <div className={"fia-logo" + (compact ? " compact" : "")}>
    <div className="logo-symbol"><span>F</span><i /></div>
    {!compact && <div className="logo-copy"><strong>FIA</strong><small>FASHION INTELLIGENCE</small></div>}
  </div>;
}

function BootScreen({ onEnter }: { onEnter: () => void }) {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const timers = [window.setTimeout(() => setPhase(1), 420),
      window.setTimeout(() => setPhase(2), 880),
      window.setTimeout(() => setPhase(3), 1320)];
    return () => timers.forEach(window.clearTimeout);
  }, []);
  const steps = ["Local workspace ready", "Discovery engines standing by", "Offer intelligence initialized"];
  return <div className="boot-screen">
    <div className="boot-orbit orbit-one" /><div className="boot-orbit orbit-two" />
    <div className="boot-card">
      <div className="boot-topline"><span>FIA / SYSTEM INITIALIZATION</span><span>v0.3.0</span></div>
      <Logo />
      <div className="boot-title"><span>YOUR STYLE.</span><strong>YOUR SIGNAL.</strong></div>
      <p className="boot-subtitle">A calmer way to discover fashion worth your attention.</p>
      <div className="boot-progress"><span style={{ width: (phase / 3 * 100) + "%" }} /></div>
      <div className="boot-steps">
        {steps.map((label, index) => <div className={index <= phase ? "boot-step done" : "boot-step"} key={label}>
          {index <= phase ? <Check size={13} /> : <span className="step-dot" />}{label}
        </div>)}
      </div>
      <button className="primary-button boot-enter" onClick={onEnter} disabled={phase < 3}>
        Enter your workspace <ArrowRight size={16} />
      </button>
      <div className="boot-foot"><LockKeyhole size={12} /> Research only · You stay in control of every purchase</div>
    </div>
    <div className="boot-corner">INDIA FIRST <span>·</span> HUMAN LED <span>·</span> EVIDENCE BASED</div>
  </div>;
}

function ProductCard({
  product, onSave, compact = false,
}: { product: Product; onSave: (p: Product) => void; compact?: boolean }) {
  const [imageFailed, setImageFailed] = useState(false);
  const discount = product.discount_percent && product.discount_percent > 0
    ? Math.round(product.discount_percent) : null;
  const saved = Boolean(product.is_saved);
  const [matches, setMatches] = useState<Product[]>([]);
  const [matchesOpen, setMatchesOpen] = useState(false);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [matchesLoaded, setMatchesLoaded] = useState(false);
  const [matchesError, setMatchesError] = useState("");

  async function toggleMatches() {
    if (matchesOpen) {
      setMatchesOpen(false);
      return;
    }
    setMatchesOpen(true);
    if (matchesLoaded || matchesLoading) return;
    setMatchesLoading(true);
    setMatchesError("");
    try {
      const result = await api<{ matches: Product[] }>(
        "/api/v1/products/" + product.id + "/matches",
      );
      setMatches(result.matches);
      setMatchesLoaded(true);
    } catch (err) {
      setMatchesError(err instanceof Error ? err.message : "Could not compare listings");
    } finally {
      setMatchesLoading(false);
    }
  }

  return <article className={"product-card" + (compact ? " compact-card" : "")}>
    <div className="product-visual">
      {product.image_url && !imageFailed
        ? <img src={product.image_url} alt={product.title} loading="lazy" onError={() => setImageFailed(true)} />
        : <div className="product-placeholder"><Shirt size={34} strokeWidth={1.2} /><span>IMAGE NOT AVAILABLE</span></div>}
      <div className="product-flags">
        {discount && <span className="discount-flag">{discount}% OFF</span>}
        {product.source === "demo" && <span className="demo-flag">DEMO</span>}
      </div>
      <button className={"save-product" + (saved ? " is-saved" : "")} title={saved ? "Remove saved item" : "Save item"} onClick={() => onSave(product)}>
        {saved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
      </button>
    </div>
    <div className="product-info">
      <div className="product-overline">
        <span>{product.retailer_name || product.retailer_domain}</span>
        <span className="trust-indicator" title={product.trust_label || "Seller evidence"}>
          <ShieldCheck size={12} /> {product.trust_label || "Unverified"}
        </span>
      </div>
      <h3>{product.title}</h3>
      <div className="product-price-row">
        <strong>{money(product.price, product.currency)}</strong>
        {product.original_price && product.price && product.original_price > product.price &&
          <del>{money(product.original_price, product.currency)}</del>}
      </div>
      <div className="product-meta-row">
        <span>{product.availability?.split("/").pop()?.replace(/_/g, " ") || "Check availability"}</span>
        <span>{product.last_seen ? relativeTime(product.last_seen) : "Recently found"}</span>
      </div>
      <div className="price-freshness-row">
        <span className={"price-freshness " + (product.price_freshness || "unknown")}>
          {product.price_freshness === "fresh" ? "PRICE FRESH" : product.price_freshness === "stale" ? "PRICE STALE" : "PRICE UNVERIFIED"}
        </span>
        <span>Checked {relativeTime(product.price_checked_at)}</span>
      </div>
      {[product.brand, product.product_type, product.colour, product.material, product.fit, product.size_label, product.gender].filter(Boolean).length > 0 &&
        <div className="product-attributes">
          {[product.brand, product.product_type, product.colour, product.material, product.fit, product.size_label, product.gender].filter(Boolean).map(value =>
            <span key={value}>{value}</span>)}
        </div>}
      {!compact && product.offer_label && <div className="offer-proof"><Tag size={12} /> {product.offer_label}</div>}
      <a className="product-link" href={product.canonical_url} target="_blank" rel="noreferrer">
        View at retailer <ArrowUpRight size={15} />
      </a>
      {product.gtin && <div className="gtin-match-wrap">
        <button className="gtin-match-toggle" onClick={() => void toggleMatches()} disabled={matchesLoading}>
          <PackageSearch size={13} />
          {matchesLoading ? "Comparing…" : matchesOpen ? "Hide matching listings" : "Compare same barcode"}
          <span>GTIN</span>
        </button>
        {matchesOpen && <div className="gtin-match-panel">
          {matchesLoading ? <small>Looking for the same GTIN across discovered retailers…</small>
            : matchesError ? <small>{matchesError}</small>
            : matches.length ? matches.map(match => <div className="gtin-match-row" key={match.id}>
              <div><strong>{match.retailer_name || match.retailer_domain}</strong>
                <small>{match.price_freshness === "fresh" ? "Fresh price" : "Price needs rechecking"}</small></div>
              <span>{money(match.price, match.currency)}</span>
              <a href={match.canonical_url} target="_blank" rel="noreferrer" aria-label="Open matching listing">
                <ExternalLink size={13} />
              </a>
            </div>) : <small>No other listing with this exact barcode has been found yet.</small>}
        </div>}
      </div>}
    </div>
  </article>;
}

function StatCard({ label, value, caption, icon: Icon, tone = "violet" }: {
  label: string; value: string | number; caption: string; icon: typeof Sparkles; tone?: string;
}) {
  return <div className="stat-card">
    <div className={"stat-icon " + tone}><Icon size={18} /></div>
    <div className="stat-value">{value}</div><div className="stat-label">{label}</div>
    <div className="stat-caption">{caption}</div>
  </div>;
}

function SectionTitle({ kicker, title, action }: { kicker: string; title: string; action?: ReactNode }) {
  return <div className="section-title">
    <div><span className="section-kicker">{kicker}</span><h2>{title}</h2></div>{action}
  </div>;
}

export default function App() {
  const [booted, setBooted] = useState(() => localStorage.getItem("fia.workspace.initialized") === "yes");
  const [view, setView] = useState<View>("overview");
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [offers, setOffers] = useState<Product[]>([]);
  const [savedProducts, setSavedProducts] = useState<Product[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [preferences, setPreferences] = useState<Preferences>({
    preferred_categories: [], preferred_brands: [], preferred_colours: [],
    sizes: {}, style_notes: "", budget_default: null, price_alert_threshold_percent: 2,
  });
  const [query, setQuery] = useState("");
  const [budget, setBudget] = useState("5000");
  const [category, setCategory] = useState("Any");
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [prefBrands, setPrefBrands] = useState("");
  const [prefColours, setPrefColours] = useState("");
  const [prefCategories, setPrefCategories] = useState("");
  const [styleNotes, setStyleNotes] = useState("");

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    try {
      const [h, s, o, saved, searches, recent, prefs, priceAlerts] = await Promise.all([
        api<Health>("/api/v1/health"),
        api<Stats>("/api/v1/stats"),
        api<Product[]>("/api/v1/offers?limit=12"),
        api<Product[]>("/api/v1/saved-products"),
        api<SavedSearch[]>("/api/v1/saved-searches"),
        api<HistoryItem[]>("/api/v1/history?limit=12"),
        api<Preferences>("/api/v1/preferences"),
        api<PriceAlert[]>("/api/v1/alerts?limit=50"),
      ]);
      setHealth(h); setStats(s); setOffers(o); setSavedProducts(saved);
      setSavedSearches(searches); setHistory(recent); setPreferences(prefs); setAlerts(priceAlerts);
      setPrefBrands(prefs.preferred_brands.join(", "));
      setPrefColours(prefs.preferred_colours.join(", "));
      setPrefCategories(prefs.preferred_categories.join(", "));
      setStyleNotes(prefs.style_notes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load FIA workspace");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!booted) return;
    void loadWorkspace();
    const timer = window.setInterval(() => { void loadWorkspace(); }, 45000);
    return () => window.clearInterval(timer);
  }, [booted, loadWorkspace]);

  const savedIds = useMemo(() => new Set(savedProducts.map(p => p.id)), [savedProducts]);
  const liveLabel = health?.live_discovery ? "LIVE DISCOVERY" : "DEMO DATA MODE";

  async function runResearch(event?: FormEvent) {
    event?.preventDefault();
    if (query.trim().length < 2 || searching) return;
    setSearching(true); setError(""); setNotice(""); setJob(null); setView("discover");
    try {
      const accepted = await api<{ job_id: string }>("/api/v1/research", {
        method: "POST",
        body: JSON.stringify({
          query: query.trim(),
          budget_max: budget ? Number(budget) : null,
          category,
          limit: 30,
          fetch_product_pages: true,
        }),
      });
      let finalJob: ResearchJob | null = null;
      for (let i = 0; i < 55; i++) {
        await new Promise(resolve => window.setTimeout(resolve, 900));
        finalJob = await api<ResearchJob>("/api/v1/research/" + accepted.job_id);
        setJob(finalJob);
        if (finalJob.status === "completed" || finalJob.status === "failed") break;
      }
      if (finalJob?.status === "failed") setError(finalJob.error || "Research could not be completed");
      else if (finalJob?.status === "completed") {
        setNotice("Research completed · " + finalJob.result_count + " listings evaluated");
        await loadWorkspace();
      } else setNotice("Research is still running. Its progress is available in History.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research request failed");
    } finally { setSearching(false); }
  }

  async function toggleSaved(product: Product) {
    try {
      if (savedIds.has(product.id)) {
        await api("/api/v1/saved-products/" + product.id, { method: "DELETE" });
        setNotice("Removed from your saved pieces");
      } else {
        await api("/api/v1/saved-products/" + product.id, { method: "POST" });
        setNotice("Added to your saved pieces");
      }
      await loadWorkspace();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update saved items"); }
  }

  async function watchSearch() {
    if (!query.trim()) return;
    try {
      await api("/api/v1/saved-searches", {
        method: "POST",
        body: JSON.stringify({ query: query.trim(), budget_max: budget ? Number(budget) : null, category }),
      });
      setNotice("Search saved · FIA will refresh it automatically while the backend is running");
      await loadWorkspace();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save search"); }
  }

  async function refreshSearch(saved: SavedSearch) {
    try {
      await api("/api/v1/saved-searches/" + saved.id + "/refresh", { method: "POST" });
      setNotice("Refresh queued for “" + saved.query + "”");
      await loadWorkspace();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not refresh search"); }
  }

  async function toggleWatch(saved: SavedSearch) {
    try {
      await api("/api/v1/saved-searches/" + saved.id, {
        method: "PUT", body: JSON.stringify({ active: !saved.active }),
      });
      await loadWorkspace();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update watch"); }
  }

  async function markAlertRead(alert: PriceAlert) {
    try {
      await api("/api/v1/alerts/" + alert.id + "/read", { method: "POST" });
      await loadWorkspace();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update alert"); }
  }

  async function savePreferences(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/v1/preferences", {
        method: "PUT",
        body: JSON.stringify({
          preferred_categories: prefCategories.split(",").map(v => v.trim()).filter(Boolean),
          preferred_brands: prefBrands.split(",").map(v => v.trim()).filter(Boolean),
          preferred_colours: prefColours.split(",").map(v => v.trim()).filter(Boolean),
          sizes: preferences.sizes,
          style_notes: styleNotes,
          budget_default: preferences.budget_default,
          price_alert_threshold_percent: preferences.price_alert_threshold_percent,
        }),
      });
      setNotice("Your style profile has been saved");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save preferences"); }
  }

  function enterWorkspace() {
    localStorage.setItem("fia.workspace.initialized", "yes");
    setBooted(true);
  }

  const nav = [
    { id: "overview" as View, label: "Overview", icon: LayoutDashboard },
    { id: "discover" as View, label: "Discover", icon: Compass },
    { id: "offers" as View, label: "Live offers", icon: Tag, count: stats.offers },
    { id: "alerts" as View, label: "Price-drop alerts", icon: Bell, count: stats.price_alerts_unread },
    { id: "saved" as View, label: "Saved pieces", icon: Heart, count: stats.saved_products },
    { id: "history" as View, label: "Research history", icon: History },
    { id: "profile" as View, label: "Style profile", icon: SlidersHorizontal },
  ];

  if (!booted) return <BootScreen onEnter={enterWorkspace} />;

  const products = job?.products || [];
  const recentProducts = offers.slice(0, 4);

  return <div className="fia-app">
    <div className={"mobile-shade" + (mobileNav ? " show" : "")} onClick={() => setMobileNav(false)} />
    <aside className={"sidebar" + (mobileNav ? " mobile-open" : "")}>
      <div className="sidebar-head"><Logo /><button className="icon-button close-nav" onClick={() => setMobileNav(false)}><X size={17} /></button></div>
      <div className="workspace-switch"><div className="workspace-avatar">A</div><div><strong>Personal studio</strong><small>India · INR</small></div><ChevronRight size={15} /></div>
      <div className="nav-caption">YOUR WORKSPACE</div>
      <nav className="side-nav">{nav.map(item => {
        const Icon = item.icon;
        return <button key={item.id} className={"nav-item" + (view === item.id ? " active" : "")}
          onClick={() => { setView(item.id); setMobileNav(false); setError(""); }}>
          <Icon size={17} /><span>{item.label}</span>
          {item.count !== undefined && item.count > 0 && <small>{item.count > 99 ? "99+" : item.count}</small>}
        </button>;
      })}</nav>
      <div className="sidebar-spacer" />
      <div className="autopilot-card">
        <div className="autopilot-top"><span className="autopilot-orb"><Sparkles size={14} /></span><span>FIA AUTOPILOT</span><span className={health?.automatic_offer_refresh ? "online-dot" : "idle-dot"} /></div>
        <strong>{health?.automatic_offer_refresh ? "Offer watch is active" : "Research is ready"}</strong>
        <p>{health?.automatic_offer_refresh
          ? "Saved searches refresh in the background on the configured schedule."
          : "Connect live discovery to unlock automated offer refresh."}</p>
        <button onClick={() => setView("profile")}>Configure workspace <ArrowUpRight size={13} /></button>
      </div>
      <div className="sidebar-bottom">
        <div className="avatar">AG</div><div className="user-caption"><strong>My style space</strong><small>Local workspace</small></div>
        <button className="icon-button" onClick={() => setView("profile")} title="Style profile"><Settings2 size={16} /></button>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)}><Menu size={19} /></button>
          <div className="breadcrumb">FIA <ChevronRight size={13} /> <span>{nav.find(n => n.id === view)?.label || "Overview"}</span></div>
        </div>
        <div className="topbar-right">
          <div className={"connection-pill" + (health?.live_discovery ? " live" : "")}>
            <span />{liveLabel}
          </div>
          <button className="icon-button refresh-button" title="Refresh workspace" onClick={() => void loadWorkspace()}>
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
          <div className="top-avatar">A</div>
        </div>
      </header>

      <div className="page-content">
        {(error || notice) && <div className={"toast " + (error ? "toast-error" : "toast-success")}>
          {error ? <X size={15} /> : <Check size={15} />}{error || notice}
          <button onClick={() => { setError(""); setNotice(""); }}><X size={14} /></button>
        </div>}

        {view === "overview" && <>
          <section className="welcome-row">
            <div><div className="eyebrow"><span className="pulse-dot" /> YOUR PERSONAL FASHION INTELLIGENCE</div>
              <h1>Discover your <em>next signature.</em></h1>
              <p>Thoughtful finds. Real product details. Offers with receipts.</p>
            </div>
            <div className="date-chip"><Sparkle size={14} /> YOUR STYLE SIGNAL <span>·</span> INDIA</div>
          </section>
          <section className="hero-search">
            <div className="hero-glow" />
            <div className="hero-copy"><span className="hero-kicker"><WandSparkles size={14} /> INTELLIGENT DISCOVERY</span>
              <h2>Tell FIA what<br /><em>feels like you.</em></h2>
              <p>Describe the fit, mood, colour or occasion. FIA researches listings and compares the evidence.</p>
            </div>
            <form className="hero-form" onSubmit={runResearch}>
              <div className="hero-input"><Search size={18} /><input value={query} onChange={e => setQuery(e.target.value)}
                placeholder="e.g. relaxed linen shirts in muted earth tones" minLength={2} required />
                <kbd>↵</kbd></div>
              <div className="hero-controls">
                <label className="mini-field"><span>MAX BUDGET</span><div><span>₹</span><input value={budget} onChange={e => setBudget(e.target.value)} inputMode="numeric" placeholder="Any" /></div></label>
                <label className="mini-field category-field"><span>WHAT ARE WE EXPLORING?</span><select value={category} onChange={e => setCategory(e.target.value)}>
                  <option>Any</option><option>Clothing</option><option>Footwear</option><option>Accessories</option><option>Watches</option><option>Bags</option>
                </select></label>
                <button className="primary-button" disabled={searching}>{searching ? <LoaderCircle className="spin" size={16} /> : <Radar size={16} />}
                  {searching ? "Researching" : "Start research"} <ArrowRight size={15} /></button>
              </div>
              <div className="quick-prompts"><span>TRY A SIGNAL</span>{["Quiet luxury", "Everyday sneakers", "Office to evening"].map(p =>
                <button key={p} type="button" onClick={() => setQuery(p)}>{p}</button>)}</div>
            </form>
          </section>
          <section className="stats-grid">
            <StatCard label="DISCOVERED PIECES" value={stats.products.toLocaleString("en-IN")} caption="Across your research runs" icon={PackageSearch} />
            <StatCard label="OFFER SIGNALS" value={stats.offers.toLocaleString("en-IN")} caption="Structured prices & discounts" icon={TrendingDown} tone="mint" />
            <StatCard label="SAVED PIECES" value={stats.saved_products.toLocaleString("en-IN")} caption="Your personal shortlist" icon={Heart} tone="rose" />
            <StatCard label="RESEARCH RUNS" value={stats.completed_jobs.toLocaleString("en-IN")} caption="Completed investigations" icon={Activity} tone="blue" />
          </section>
          <section className="content-section">
            <SectionTitle kicker="THE OFFER RADAR" title="Worth a closer look"
              action={<button className="text-action" onClick={() => setView("offers")}>Explore all offers <ArrowRight size={14} /></button>} />
            {recentProducts.length ? <div className="product-grid">{recentProducts.map(p =>
              <ProductCard key={p.id} product={{ ...p, is_saved: savedIds.has(p.id) }} onSave={toggleSaved} compact />)}</div>
              : <div className="empty-panel"><div className="empty-icon"><Tag size={22} /></div>
                <div><strong>No verified offer signals yet</strong><p>Connect a live search provider and research products to populate this feed from retailer data.</p></div>
                <button className="secondary-button" onClick={() => setView("discover")}>Start discovering <ArrowRight size={14} /></button></div>}
          </section>
          <section className="bottom-grid">
            <div className="content-section"><SectionTitle kicker="YOUR RESEARCH TRAIL" title="Recently explored"
              action={<button className="text-action" onClick={() => setView("history")}>View history <ArrowRight size={14} /></button>} />
              {history.length ? <div className="activity-list">{history.slice(0, 5).map(h => <button className="activity-item" key={h.job_id}
                onClick={() => { setQuery(h.query); setView("discover"); }}>
                <div className="activity-icon"><Search size={15} /></div><div><strong>{h.query}</strong><small>{relativeTime(h.created_at)} · {h.result_count} listings</small></div>
                <span className={"job-status " + h.status}>{h.status}</span><ChevronRight size={15} />
              </button>)}</div> : <div className="subtle-empty">Your research sessions will appear here.</div>}
            </div>
            <div className="content-section watch-summary"><SectionTitle kicker="ALWAYS ON, ON YOUR TERMS" title="Search watches" />
              {savedSearches.length ? savedSearches.slice(0, 4).map(w => <div className="watch-line" key={w.id}>
                <div className="watch-icon"><Radar size={15} /></div><div className="watch-details"><strong>{w.query}</strong><small>{w.active ? "Monitoring" : "Paused"} · {relativeTime(w.last_run_at)}</small></div>
                <span className={w.active ? "watch-led active" : "watch-led"} />
              </div>) : <div className="subtle-empty">Save a search to let FIA refresh it automatically.</div>}
              <button className="secondary-button full-button" onClick={() => setView("saved")}>Manage saved searches <ArrowRight size={14} /></button>
            </div>
          </section>
        </>}

        {view === "discover" && <>
          <section className="page-heading"><div><span className="section-kicker">THE OPEN-WEB RESEARCH DESK</span><h1>Find the <em>right piece.</em></h1>
            <p>FIA searches, inspects permitted product pages and ranks the evidence.</p></div><div className="heading-mark"><Compass size={24} /></div></section>
          <section className="search-console">
            <form onSubmit={runResearch}>
              <div className="console-query"><Search size={19} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Describe the product, aesthetic or occasion..." required minLength={2} /></div>
              <div className="console-bottom">
                <label><span>MAX BUDGET</span><div className="input-shell">₹<input value={budget} onChange={e => setBudget(e.target.value)} inputMode="numeric" placeholder="No limit" /></div></label>
                <label><span>CATEGORY</span><select value={category} onChange={e => setCategory(e.target.value)}><option>Any</option><option>Clothing</option><option>Footwear</option><option>Accessories</option><option>Watches</option><option>Bags</option></select></label>
                <button className="primary-button" disabled={searching}>{searching ? <LoaderCircle className="spin" size={16} /> : <Radar size={16} />}{searching ? "Researching" : "Research the web"}<ArrowRight size={15} /></button>
                <button type="button" className="secondary-button" onClick={watchSearch}><Bookmark size={15} /> Watch this search</button>
              </div>
            </form>
          </section>
          {searching && <div className="research-progress"><div className="progress-orb"><Radar size={20} className="spin" /></div>
            <div><strong>FIA is investigating the market…</strong><p>Searching retailer listings, inspecting available product data and evaluating evidence.</p></div></div>}
          {job && <div className="results-heading"><div><span className="section-kicker">RESEARCH ID {job.job_id.slice(0, 8).toUpperCase()}</span>
            <h2>{job.query}</h2><p>{job.status} · {job.result_count} listing signals</p></div>
            <span className={"job-status " + job.status}>{job.status}</span></div>}
          {job?.products?.length ? <div className="product-grid results-grid">{job.products.map(p =>
            <ProductCard key={p.id} product={{ ...p, is_saved: savedIds.has(p.id) }} onSave={toggleSaved} />)}</div>
            : !searching && <div className="empty-panel large-empty"><div className="empty-icon"><Sparkles size={24} /></div>
              <div><strong>Your next discovery starts with a prompt</strong><p>Try a clear description such as “women's black leather shoulder bag under ₹4,000”.</p></div></div>}
        </>}

        {view === "offers" && <>
          <section className="page-heading"><div><span className="section-kicker">PRICE & PROMOTION INTELLIGENCE</span><h1>Offers with <em>evidence.</em></h1>
            <p>Discounts shown here come from observed retailer product data, not estimated promo claims.</p></div>
            <button className="secondary-button" onClick={() => void loadWorkspace()}><RefreshCw size={15} /> Refresh feed</button></section>
          {offers.length ? <div className="product-grid">{offers.map(p =>
            <ProductCard key={p.id} product={{ ...p, is_saved: savedIds.has(p.id) }} onSave={toggleSaved} />)}</div>
            : <div className="empty-panel large-empty"><div className="empty-icon"><CircleDollarSign size={24} /></div>
              <div><strong>No structured discounts found yet</strong><p>When retailers expose original price and current offer information on accessible product pages, FIA will surface the difference here.</p></div>
              <button className="primary-button" onClick={() => setView("discover")}>Research a product <ArrowRight size={15} /></button></div>}
          <p className="disclaimer-line"><ShieldCheck size={13} /> Prices and availability can change. Always confirm on the retailer site before buying.</p>
        </>}

        {view === "alerts" && <>
          <section className="page-heading"><div><span className="section-kicker">YOUR SAVED-PIECE SIGNALS</span>
            <h1>Price drops, <em>delivered.</em></h1>
            <p>FIA alerts you when a refreshed listing confirms a lower price for a product you saved.</p></div>
            <button className="secondary-button" onClick={() => void loadWorkspace()}><RefreshCw size={15} /> Sync alerts</button></section>
          <div className="price-alert-list">
            {alerts.length ? alerts.map(alert => <article className={"price-alert-card" + (alert.read_at ? "" : " unread")} key={alert.id}>
              <div className="price-alert-symbol"><TrendingDown size={19} /></div>
              <div className="price-alert-copy"><span>PRICE DROP · {alert.drop_percent}% LOWER</span><h3>{alert.title}</h3>
                <p>{money(alert.previous_price, alert.currency)} <ArrowRight size={13} /> <strong>{money(alert.current_price, alert.currency)}</strong></p>
                <a href={alert.canonical_url} target="_blank" rel="noreferrer">Check retailer listing <ExternalLink size={13} /></a>
              </div>
              <div className="price-alert-meta"><strong>{money(alert.current_price, alert.currency)}</strong><small>{relativeTime(alert.created_at)}</small>
                {!alert.read_at && <button className="secondary-button small-button" onClick={() => void markAlertRead(alert)}>Mark read</button>}
                {alert.read_at && <small className="alert-read-label"><Check size={12} /> Read</small>}
              </div>
            </article>) : <div className="empty-panel large-empty"><div className="empty-icon"><Bell size={23} /></div>
              <div><strong>No price-drop alerts yet</strong><p>Save a product and keep an active search watch running. FIA will add an alert here when a lower price is observed.</p></div>
              <button className="primary-button" onClick={() => setView("saved")}>View saved pieces <ArrowRight size={15} /></button></div>}
          </div>
        </>}

        {view === "saved" && <>
          <section className="page-heading"><div><span className="section-kicker">YOUR PERSONAL SHORTLIST</span><h1>Pieces to <em>remember.</em></h1>
            <p>Keep products and monitor searches you want FIA to revisit.</p></div><div className="heading-mark"><BookmarkCheck size={23} /></div></section>
          <div className="content-section saved-section"><SectionTitle kicker="BOOKMARKED PRODUCTS" title="Your saved pieces" />
            {savedProducts.length ? <div className="product-grid">{savedProducts.map(p =>
              <ProductCard key={p.id} product={{ ...p, is_saved: true }} onSave={toggleSaved} />)}</div>
              : <div className="subtle-empty">Save a product from any card to build your shortlist.</div>}
          </div>
          <div className="content-section saved-section"><SectionTitle kicker="AUTOMATED RESEARCH" title="Search watches" />
            {savedSearches.length ? <div className="saved-search-list">{savedSearches.map(s => <div className="saved-search-row" key={s.id}>
              <div className="saved-search-icon"><Radar size={18} /></div><div className="saved-search-copy"><strong>{s.query}</strong>
                <small>{s.category || "Any category"}{s.budget_max ? " · Up to " + money(s.budget_max) : ""} · Last scan {relativeTime(s.last_run_at)}</small></div>
              <span className={"watch-state " + (s.active ? "is-active" : "")}>{s.active ? "ACTIVE" : "PAUSED"}</span>
              <button className="icon-button" title="Refresh now" onClick={() => refreshSearch(s)}><RefreshCw size={15} /></button>
              <button className="secondary-button small-button" onClick={() => toggleWatch(s)}>{s.active ? "Pause" : "Resume"}</button>
            </div>)}</div> : <div className="subtle-empty">Use “Watch this search” to have FIA refresh it automatically.</div>}
          </div>
        </>}

        {view === "history" && <>
          <section className="page-heading"><div><span className="section-kicker">YOUR DISCOVERY LOG</span><h1>Research <em>history.</em></h1>
            <p>Every search run, its status and the number of listings returned.</p></div><button className="secondary-button" onClick={() => void loadWorkspace()}><RefreshCw size={15} /> Sync history</button></section>
          <div className="history-table">
            <div className="history-head"><span>RESEARCH QUERY</span><span>STATUS</span><span>LISTINGS</span><span>STARTED</span></div>
            {history.map(h => <button className="history-row" key={h.job_id} onClick={() => { setQuery(h.query); setView("discover"); }}>
              <div><span className="history-query-icon"><Search size={14} /></span><strong>{h.query}</strong></div>
              <span className={"job-status " + h.status}>{h.status}</span><span>{h.result_count}</span><span>{relativeTime(h.created_at)}</span>
            </button>)}
            {!history.length && <div className="subtle-empty">No research runs yet. Your first search will appear here.</div>}
          </div>
        </>}

        {view === "profile" && <>
          <section className="page-heading"><div><span className="section-kicker">THE DETAILS THAT MAKE IT YOURS</span><h1>Your style <em>signature.</em></h1>
            <p>Set preferences that can guide future discovery and ranking.</p></div><div className="heading-mark"><SlidersHorizontal size={23} /></div></section>
          <div className="profile-layout">
            <form className="profile-form" onSubmit={savePreferences}>
              <div className="form-section"><span className="section-kicker">STYLE SIGNALS</span><h3>What do you gravitate towards?</h3>
                <label>FAVOURITE CATEGORIES<input value={prefCategories} onChange={e => setPrefCategories(e.target.value)} placeholder="Streetwear, footwear, smart casual" /></label>
                <label>BRANDS YOU LIKE<input value={prefBrands} onChange={e => setPrefBrands(e.target.value)} placeholder="Nike, Zara, Uniqlo" /></label>
                <label>COLOURS YOU REACH FOR<input value={prefColours} onChange={e => setPrefColours(e.target.value)} placeholder="Black, cream, olive, navy" /></label>
                <label>YOUR STYLE IN YOUR WORDS<textarea value={styleNotes} onChange={e => setStyleNotes(e.target.value)} rows={4} placeholder="Describe the silhouettes, fabrics, fits and moods you prefer…" /></label>
              </div>
              <div className="form-section"><span className="section-kicker">AUTOMATION</span><h3>Research behaviour</h3>
                <label className="alert-threshold-field">MINIMUM VERIFIED PRICE DROP TO ALERT
                  <div><input type="number" min="0" max="100" step="0.5"
                    value={preferences.price_alert_threshold_percent}
                    onChange={e => setPreferences(current => ({
                      ...current, price_alert_threshold_percent: Number(e.target.value),
                    }))} /><span>%</span></div>
                  <small>Only same-currency drops meeting this threshold create an alert. Repeated alerts are grouped by a {health?.price_alert_cooldown_hours ?? 24}-hour cooldown. Prices older than {health?.price_stale_after_hours ?? 72} hours are marked stale.</small>
                </label>
                <div className="automation-info"><div className="automation-icon"><Zap size={17} /></div><div><strong>{health?.automatic_offer_refresh ? "Automatic refresh enabled" : "Live refresh is waiting for a provider"}</strong>
                  <p>{health?.automatic_offer_refresh ? "Active saved searches refresh every " + Math.round(health.refresh_interval_minutes / 60) + " hours while FIA is running." : "Demo mode is local-only. Add your Brave Search API key and switch the provider to enable live discovery and watch refreshes."}</p></div></div>
              </div>
              <button className="primary-button" type="submit"><Check size={16} /> Save style profile</button>
            </form>
            <aside className="profile-side">
              <div className="profile-card"><div className="profile-monogram">A</div><span className="section-kicker">LOCAL STYLE PROFILE</span><h3>Personal studio</h3><p>Your profile stays in your local FIA database. No store accounts or purchase permissions are connected.</p>
                <div className="privacy-line"><LockKeyhole size={14} /> Research-only workspace</div></div>
              <div className="profile-card small"><span className="section-kicker">DISCOVERY SOURCE</span><strong>{health?.live_discovery ? "Brave Search · India" : "Demo provider"}</strong>
                <p>Images and offer data are only displayed when a source returns usable metadata.</p></div>
            </aside>
          </div>
        </>}
        <footer className="app-footer"><span><Logo compact /> FIA / FASHION INTELLIGENCE AGENT</span>
          <span>Evidence-led discovery <i /> Human-approved purchases <i /> India first</span></footer>
      </div>
    </main>
  </div>;
}
