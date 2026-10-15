import { useEffect, useState } from "react";
import { Search, Sparkles, ShieldCheck, IndianRupee, Shirt, History, Settings2, ArrowUpRight, LoaderCircle, Radar, Heart } from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
type Product = {id?:number;title:string;canonical_url:string;description?:string;brand?:string;image_url?:string;price?:number;currency:string;retailer_domain:string;retailer_name?:string;source:string;trust_label:string;trust_score:number;reasons:string[]};
type Job = {job_id:string;status:string;query:string;result_count:number;error?:string;products:Product[]};

export default function App() {
 const [query,setQuery]=useState(""); const [budget,setBudget]=useState("3000");
 const [category,setCategory]=useState("Footwear"); const [job,setJob]=useState<Job|null>(null);
 const [busy,setBusy]=useState(false); const [error,setError]=useState(""); const [health,setHealth]=useState("Checking");
 useEffect(()=>{fetch(API+"/api/v1/health").then(r=>r.json()).then(d=>setHealth(d.provider==="demo"?"Demo mode":"Connected")).catch(()=>setHealth("Offline"));},[]);
 async function research(e:React.FormEvent){
  e.preventDefault();if(query.trim().length<2)return;setBusy(true);setError("");setJob(null);
  try{
   const response=await fetch(API+"/api/v1/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,budget_max:budget?Number(budget):null,category,limit:25,fetch_product_pages:true})});
   if(!response.ok)throw new Error((await response.text()).slice(0,300));
   const accepted=await response.json();let current:Job|null=null;
   for(let i=0;i<40;i++){await new Promise(resolve=>setTimeout(resolve,700));const result=await fetch(API+"/api/v1/research/"+accepted.job_id);const next:Job=await result.json();current=next;setJob(next);if(["completed","failed"].includes(next.status))break;}
   if(current?.status==="failed")setError(current.error||"Research failed");
  }catch(err){setError(err instanceof Error?err.message:"Unable to contact FIA API");}
  finally{setBusy(false);}
 }
 const products=job?.products||[];
 return <div className="app-shell">
  <aside className="sidebar"><div className="brand"><div className="brand-mark">F</div><div><b>FIA</b><span>FASHION INTELLIGENCE</span></div></div>
   <div className="side-label">WORKSPACE</div><a className="nav active"><Search size={17}/> Discover</a><a className="nav"><Heart size={17}/> Saved research</a><a className="nav"><History size={17}/> History</a>
   <div className="side-bottom"><div className="mode"><span className="pulse"/> RESEARCH MODE</div><p>India-first product discovery. No checkout or purchases.</p><div className="profile"><div className="avatar">A</div><div><b>Personal workspace</b><small>Local profile</small></div><Settings2 size={17}/></div></div>
  </aside>
  <main className="main"><header><div><span className="eyebrow">YOUR PERSONAL SHOPPING RESEARCHER</span><h1>Find your next <em>favourite.</em></h1><p>Search across the open web. Compare the details. Buy with confidence.</p></div><div className="status"><span className={health==="Offline"?"dot off":"dot"}/>{health}</div></header>
   <section className="search-panel"><div className="panel-heading"><div className="spark"><Sparkles size={18}/></div><div><b>What are we looking for?</b><small>Describe the item, aesthetic, or outfit in your own words.</small></div></div>
    <form onSubmit={research}><div className="query-wrap"><Search size={19}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. minimal white sneakers for everyday wear..." required minLength={2}/><kbd>↵</kbd></div>
     <div className="filters"><label>MAX BUDGET<div className="budget"><IndianRupee size={14}/><input value={budget} onChange={e=>setBudget(e.target.value)} inputMode="numeric" placeholder="No limit"/></div></label><label>CATEGORY<select value={category} onChange={e=>setCategory(e.target.value)}><option>Footwear</option><option>Clothing</option><option>Accessories</option><option>Watches</option><option>Bags</option><option>Any</option></select></label><button disabled={busy||query.trim().length<2}>{busy?<><LoaderCircle className="spin" size={17}/> Researching</>:<><Radar size={17}/> Start discovery</>}</button></div>
    </form></section>
   <section className="section-head"><div><span className="eyebrow">RESEARCH RESULTS</span><h2>{busy?"Investigating the web":job?"Your shortlist":"Ready when you are"}</h2></div>{job&&<span className="result-count">{job.status} · {job.result_count} results</span>}</section>
   {error&&<div className="error">{error}</div>}
   {!job&&!busy&&<div className="empty"><div className="empty-icon"><Shirt size={27}/></div><h3>Your next great find starts here.</h3><p>Tell FIA what you have in mind. It will gather listings, assess domain evidence and rank relevant matches.</p><div className="chips">{["Quiet luxury shirts","Everyday sneakers","Minimal silver accessories"].map(s=><button key={s} onClick={()=>setQuery(s)}>{s} <ArrowUpRight size={13}/></button>)}</div></div>}
   {busy&&!products.length&&<div className="loading"><LoaderCircle className="spin" size={24}/><b>Searching and evaluating listings…</b><span>Checking provider results and available product details.</span></div>}
   {products.length>0&&<div className="grid">{products.map((p,i)=><article className="product" key={p.id||p.canonical_url}><div className="product-image">{p.image_url?<img src={p.image_url} alt="" loading="lazy"/>:<div className="image-placeholder"><Shirt size={34}/></div>}<span className="rank">0{i+1}</span></div><div className="product-body"><div className="merchant">{p.retailer_name||p.retailer_domain}<span className="trust"><ShieldCheck size={13}/>{p.trust_label}</span></div><h3>{p.title}</h3><div className="price">{p.price!=null?<><IndianRupee size={15}/>{p.price.toLocaleString("en-IN")}</>:<span>Price unavailable</span>}</div><p className="description">{p.description||"No additional product description was available."}</p><div className="evidence">{p.reasons.slice(0,2).map((reason,j)=><span key={j}>{reason}</span>)}</div><a className="open-link" href={p.canonical_url} target="_blank" rel="noreferrer">Inspect retailer listing <ArrowUpRight size={15}/></a></div></article>)}</div>}
   {job&&job.status==="completed"&&products.length===0&&<div className="empty"><h3>No product listings yet</h3><p>Try a broader query or configure a live search provider. Demo mode only returns illustrative listings.</p></div>}
   <footer><span>FIA · FASHION INTELLIGENCE AGENT</span><span>Evidence-led research · Human makes every purchase</span></footer>
  </main>
 </div>;
}
