import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, MotionConfig } from 'motion/react';
import * as Tabs from '@radix-ui/react-tabs';
import { Activity, ArrowDownToLine, ArrowRight, Check, CheckCheck, ChevronRight, CircleDot, Code2, FileCode2, FlaskConical, GitBranch, Layers3, Loader2, Moon, Plus, Radar, ShieldCheck, Square, Sun, Terminal, TriangleAlert, Wifi, WifiOff } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from './components/button';
import type { components } from './generated/api';

const Diff = lazy(() => import('./Diff'));
const Flow = lazy(() => import('./Flow'));
type Run = components['schemas']['RunView'];
type Repo = { id: string; name: string; fixture: string; commit_sha: string; targets: {id: string; verification: string}[] };
type Citation = {path: string; text: string; start_line: number; end_line: number};
type Event = {sequence: number; type: string; timestamp: string; payload: Record<string, unknown>};
const formSchema = z.object({fixture:z.string().min(1), title:z.string().min(3,'Use at least 3 characters').max(200), description:z.string().max(8000)});
type Form = z.infer<typeof formSchema>;
const terminal = new Set(['needs_review', 'cancelled', 'failed', 'completed']);
const human = (s: string) => s.replaceAll('_',' ').replaceAll('.',' · ');
async function api<T>(path: string, init?: RequestInit): Promise<T> {
 const response = await fetch(`/api/v1${path}`, {...init, credentials:'same-origin', headers:{'Content-Type':'application/json', ...init?.headers}});
 if (!response.ok) { const error = await response.json().catch(()=>({message:`HTTP ${response.status}`})); throw new Error(error.message ?? error.detail ?? `HTTP ${response.status}`); }
 return response.json();
}

export default function App() {
 const client = useQueryClient();
 const [selected, select] = useState<string|null>(null);
 const [section, setSection] = useState('hunts');
 const [light, setLight] = useState(false);
 const [connected, setConnected] = useState(false);
 const [events, setEvents] = useState<Event[]>([]);
 const [file, setFile] = useState(0);
 const cursor = useRef(0);
 const session = useQuery({queryKey:['session'], queryFn:({signal})=>api('/session',{signal})});
 const repos = useQuery({queryKey:['repositories'],queryFn:({signal})=>api<Repo[]>('/repositories',{signal}),enabled:session.isSuccess});
 const runs = useQuery({queryKey:['runs'],queryFn:({signal})=>api<Run[]>('/runs',{signal}),enabled:session.isSuccess,refetchInterval:3000});
 const run = useQuery({queryKey:['run',selected],queryFn:({signal})=>api<Run>(`/runs/${selected}`,{signal}),enabled:!!selected&&session.isSuccess,refetchInterval:3000});
 const evidence = useQuery({queryKey:['evidence',selected],queryFn:({signal})=>api<{citations:Citation[]}>(`/runs/${selected}/evidence`,{signal}),enabled:!!selected&&session.isSuccess});
 const form = useForm<Form>({resolver:zodResolver(formSchema),defaultValues:{fixture:'python-boundary',title:'Inclusive boundary excludes the maximum',description:'A value equal to the maximum should be included. Preserve lower and out-of-range behavior.'}});
 const start = useMutation({mutationFn:(body:Form)=>api<Run>('/runs',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)}),onSuccess:(data)=>{select(data.id);client.invalidateQueries({queryKey:['runs']});}});
 const cancel = useMutation({mutationFn:()=>api(`/runs/${selected}/cancel`,{method:'POST'}),onSuccess:()=>client.invalidateQueries({queryKey:['run',selected]})});
 useEffect(()=>{document.documentElement.dataset.theme=light?'light':'dark';},[light]);
 useEffect(()=>{
   setEvents([]);cursor.current=0;setConnected(false);setFile(0);
   if (!selected) return;
   const stream = new EventSource(`/api/v1/runs/${selected}/events`);
   stream.onopen=()=>setConnected(true);stream.onerror=()=>setConnected(false);
   const receive=(message:MessageEvent)=>{const e=JSON.parse(message.data) as Event;if(e.sequence<=cursor.current)return;cursor.current=e.sequence;setEvents(prev=>[...prev.slice(-99),e]);client.invalidateQueries({queryKey:['run',selected]});client.invalidateQueries({queryKey:['evidence',selected]});};
   ['run.queued','execution.waiting','review.ready','run.cancellation_requested','run.cancelled','execution.completed'].forEach(type=>stream.addEventListener(type,receive as EventListener));
   return()=>stream.close();
 },[selected,client]);
 const current=run.data;
 const citations=evidence.data?.citations??[];
 const citation=citations[file];
 const active=(runs.data??[]).filter(r=>!terminal.has(r.status)).length;
 const error=session.error??repos.error??runs.error??run.error??start.error??cancel.error;
 return <MotionConfig reducedMotion="user"><div className="shell">
  <aside className="sidebar">
   <a className="brand" href="#main" aria-label="RepoReaper home"><span className="brand-mark"><Radar size={24}/></span><span>Repo<span className="brand-subtle">Reaper</span></span></a>
   <div className="workspace-switch"><span className="workspace-avatar">L</span><div><strong>Local lab</strong><small>Development workspace</small></div><Layers3 size={16}/></div>
   <div className="nav-caption">WORKSPACE</div>
   <nav aria-label="Main navigation"><button className={section==='hunts'?'nav-item active':'nav-item'} onClick={()=>setSection('hunts')}><Radar size={18}/>Investigations<span className="nav-count">{runs.data?.length??'—'}</span></button><button className={section==='repos'?'nav-item active':'nav-item'} onClick={()=>setSection('repos')}><GitBranch size={18}/>Repositories</button></nav>
   <div className="sidebar-note"><ShieldCheck size={18}/><strong>Evidence over assumptions.</strong><p>Every verdict traces back to a snapshot and an isolated check.</p></div>
   <div className="sidebar-footer"><span className="user-avatar">LD</span><div><strong>Local developer</strong><small>Single-owner demo</small></div><Button variant="ghost" onClick={()=>setLight(v=>!v)} aria-label={light?'Use dark theme':'Use light theme'}>{light?<Moon size={16}/>:<Sun size={16}/>}</Button></div>
  </aside>
  <div className="main-shell"><header className="topbar"><span className="breadcrumb">Workspace <ChevronRight size={13}/><strong>{section==='hunts'?'Investigations':'Repositories'}</strong></span><span className="environment"><span className="dot"/> LOCAL ENVIRONMENT</span></header>
  <main id="main">
   <div className="page-heading"><div><div className="eyebrow">HUNT THE BUG. PROVE THE FIX.</div><h1>{section==='hunts'?'The investigation desk.':'Know your execution coverage.'}</h1><p>{section==='hunts'?'From a reported failure to a reviewable change. Every step leaves evidence.':'Immutable sources. Independent language targets. Explicit verification profiles.'}</p></div><span className="mode-badge"><FlaskConical size={15}/> Deterministic fixture lab</span></div>
   {error&&<div className="error-panel" role="alert"><TriangleAlert size={20}/><div><strong>Connection or request needs attention</strong><p>{error.message}</p><Button variant="outline" onClick={()=>client.invalidateQueries()}>Reconnect</Button></div></div>}
   {session.isPending&&<div className="loading" role="status"><Loader2 className="spin"/>Connecting to the workspace…</div>}
   {section==='repos'?<div className="repo-grid">{repos.data?.map(repo=><article className="panel repo-card" key={repo.id}><GitBranch size={22}/><h2>{repo.name}</h2><code>{repo.commit_sha.slice(0,12)}</code><div className="target-list">{repo.targets.map(t=><div key={t.id}><Code2 size={15}/><strong>{t.id}</strong><span className={t.verification==='available'?'ok':'uncertain'}>{human(t.verification)}</span></div>)}</div><Button variant="outline" onClick={()=>{form.setValue('fixture',repo.fixture);setSection('hunts');select(null);}}>Investigate this fixture <ArrowRight size={15}/></Button></article>)}</div>:<>
   <div className="status-strip"><div><span className="icon-well"><Activity size={18}/></span><div><strong>{active}</strong><span>active investigations</span></div></div><div><span className="icon-well"><GitBranch size={18}/></span><div><strong>{repos.data?.length??'—'}</strong><span>curated repositories</span></div></div><p><FlaskConical size={16}/> Scripted model. Real persistence and sandbox checks.</p></div>
   <div className="desk-layout">
   <section className="run-list panel"><div className="panel-heading"><h2>Investigations</h2><Button variant="ghost" aria-label="Create investigation" onClick={()=>select(null)}><Plus size={17}/></Button></div><button className={!selected?'new-run selected':'new-run'} onClick={()=>select(null)}><Plus size={16}/> New investigation</button>
   {runs.isPending&&session.isSuccess&&<p className="muted pad" role="status">Loading investigations…</p>}
   {runs.data?.length===0&&<div className="empty-mini"><Radar size={28}/><p>A clean slate.<br/>Start your first fixture hunt.</p></div>}
   {runs.data?.map(item=><button key={item.id} className={`run-item ${selected===item.id?'selected':''}`} onClick={()=>select(item.id)}><div><span className={`dot ${item.outcome==='verified_fix'?'green':item.status==='failed'?'red':''}`}/><span className="run-status">{human(item.status)}</span></div><strong>{item.title}</strong><small>{item.fixture}</small><div className="run-id"><code>{item.id.slice(0,8)}</code><ArrowRight size={14}/></div></button>)}
   </section>
   {!selected?<motion.section className="new-hunt panel" initial={{opacity:0,y:8}} animate={{opacity:1,y:0}}><div className="panel-heading"><div><span className="eyebrow">START WITH A FAILURE</span><h2>A new investigation</h2></div><Radar size={30} className="violet"/></div><p className="muted">Choose an immutable fixture and describe the behavior. The lab investigates a known boundary bug through the real workflow.</p><form onSubmit={form.handleSubmit(body=>start.mutate(body))}><label htmlFor="repository">Repository</label><select id="repository" {...form.register('fixture')}>{repos.data?.map(r=><option key={r.id} value={r.fixture}>{r.name} · {r.commit_sha.slice(0,8)}</option>)}</select><label htmlFor="title">Issue title</label><input id="title" {...form.register('title')}/>{form.formState.errors.title&&<small role="alert" className="red">{form.formState.errors.title.message}</small>}<label htmlFor="description">Expected behavior & context</label><textarea id="description" rows={4} {...form.register('description')}/><div className="fixture-disclosure"><ShieldCheck size={18}/><p>Curated sources only. Python and Node run in disposable, network-isolated containers. Mixed React coverage is explicitly partial in M0.</p></div><Button disabled={start.isPending||!repos.data?.length} type="submit">{start.isPending?<Loader2 className="spin" size={16}/>:<Radar size={16}/>} {start.isPending?'Persisting investigation…':'Start investigation'}<ArrowRight size={16}/></Button></form></motion.section>:
   <section className="investigation panel">{!current?<div className="loading" role="status"><Loader2 className="spin"/>Loading investigation…</div>:<>
    <div className="investigation-heading"><div><div className="run-meta"><code>RUN / {current.id.slice(0,8)}</code><span className={`state-badge ${current.outcome==='verified_fix'?'success':''}`}>{human(current.status)}</span></div><h2>{current.title}</h2><div className="source-meta"><GitBranch size={14}/>{current.fixture}<span>·</span><code title={current.base_sha}>{current.base_sha.slice(0,12)}</code></div></div>{!terminal.has(current.status)&&<Button variant="outline" disabled={cancel.isPending||current.status==='cancelling'} onClick={()=>cancel.mutate()}><Square size={12}/>{current.status==='cancelling'?'Cancelling…':'Cancel'}</Button>}</div>
    <div className="coverage-row">{current.targets.map((t,i)=><span key={i} className={t.profile?'target-chip':'target-chip uncertain'}><Code2 size={13}/>{String(t.id)} <span>{t.profile?'isolated profile':'verification missing'}</span></span>)}<span className={`connection ${connected?'':'uncertain'}`} aria-live="polite">{connected?<Wifi size={13}/>:<WifiOff size={13}/>} {connected?'Live events':'Reconnecting'}</span></div>
    {current.outcome&&<div className={`verdict ${current.outcome==='verified_fix'?'passed':'partial'}`} role="status">{current.outcome==='verified_fix'?<CheckCheck size={23}/>:<TriangleAlert size={23}/>}<div><strong>{human(current.outcome)}</strong><p>{current.outcome==='verified_fix'?'The original boundary failure was observed on base; patched reproduction and regression checks passed.':current.outcome==='partial_verification'?'Python checks passed. The React target lacks a runtime profile, so the mixed patch remains partially verified.':'Review the observed execution evidence and limitations before using this patch.'}</p></div></div>}
    <Tabs.Root defaultValue="evidence"><Tabs.List className="tab-list" aria-label="Investigation details"><Tabs.Trigger value="evidence"><ShieldCheck size={15}/>Evidence <span>{current.evidence.length}</span></Tabs.Trigger><Tabs.Trigger value="patch"><FileCode2 size={15}/>Patch diff</Tabs.Trigger><Tabs.Trigger value="timeline"><Activity size={15}/>Activity</Tabs.Trigger><Tabs.Trigger value="workflow"><Layers3 size={15}/>Workflow</Tabs.Trigger></Tabs.List>
    <Tabs.Content value="evidence" className="tab-content"><div className="evidence-heading"><h3>Observed execution evidence</h3><span className="subtle">Immutable evaluator · actual exit codes</span></div>{!current.evidence.length?<div className="waiting-state"><span className="scan-icon"><Radar size={32}/></span><h3>{current.status==='cancelled'?'Investigation cancelled':'Gathering the first evidence.'}</h3><p>Execution results appear after the runner completes and persists them.</p></div>:<div className="evidence-grid">{current.evidence.map((item,i)=><article className="evidence-card" key={i}><div className="evidence-card-heading"><span className={item.exit_code===0?'ok':'uncertain'}>{item.exit_code===0?<Check size={17}/>:<CircleDot size={17}/>} {human(String(item.phase))}</span><code>{String(item.target)}</code></div><strong>{item.exit_code===0?'Checks passed':item.expected_failure?'Original boundary failure reproduced':human(String(item.status))}</strong><div className="execution-meta"><span>Exit {String(item.exit_code??'—')}</span><span>{Number(item.duration_seconds).toFixed(2)}s</span><span>{item.cleaned?'Sandbox removed':'Cleanup pending'}</span></div><details><summary><Terminal size={13}/> Raw bounded log</summary>{item.log_artifact_id?<a className="log-download" href={`/api/v1/artifacts/${String(item.log_artifact_id)}/download`} target="_blank" rel="noreferrer">Open recorded log <ArrowRight size={12}/></a>:<pre>{String(item.log)}</pre>}</details></article>)}</div>}<div className="evidence-heading"><h3>Source citations</h3><span className="subtle">Base snapshot {current.base_sha.slice(0,8)}</span></div>{citations.map(c=><article className="citation" key={c.path}><div><FileCode2 size={15}/><code>{c.path}:{c.start_line}–{c.end_line}</code></div><pre>{c.text}</pre></article>)}</Tabs.Content>
    <Tabs.Content value="patch" className="tab-content"><div className="evidence-heading"><h3>Review the change</h3>{current.patch&&<Button variant="outline" asChild><a href={`/api/v1/patches/${current.id}/diff`} download><ArrowDownToLine size={14}/>Export patch</a></Button>}</div>{!current.patch?<div className="waiting-state"><FileCode2 size={30}/><h3>No patch yet.</h3><p>Patch preparation follows the baseline reproduction.</p></div>:<><div className="file-tabs">{citations.map((c,i)=><button aria-pressed={file===i} key={c.path} onClick={()=>setFile(i)}>{c.path}</button>)}</div>{citation&&<Suspense fallback={<p className="loading">Loading code review editor…</p>}><Diff original={citation.text} modified={citation.text.replace('< maximum','<= maximum')} language={citation.path.endsWith('.py')?'python':'typescript'} light={light}/></Suspense>}<details className="raw-diff"><summary>Unified diff & patch hash</summary><code>{current.patch_sha256}</code><pre>{current.patch}</pre></details><p className="review-note"><TriangleAlert size={15}/>Fixture harness coverage only. Export is available; external publication is disabled.</p></>}</Tabs.Content>
    <Tabs.Content value="timeline" className="tab-content"><h3>Durable activity</h3>{events.length===0?<p className="muted">Waiting for event replay…</p>:<ol className="timeline">{events.map(e=><li key={e.sequence}><span className="timeline-node"/><div><strong>{human(e.type)}</strong><p>{e.payload.outcome?human(String(e.payload.outcome)):e.payload.execution_id?`Execution ${String(e.payload.execution_id).slice(0,8)}`:'Committed to PostgreSQL'}</p></div><time>{new Date(e.timestamp).toLocaleTimeString()}</time><code>#{e.sequence}</code></li>)}</ol>}</Tabs.Content>
    <Tabs.Content value="workflow" className="tab-content"><Suspense fallback={<p className="loading">Loading workflow…</p>}><Flow status={current.status}/></Suspense><p className="muted">Execution waits release the graph worker. Node completion and verification coverage are shown in the evidence tab.</p></Tabs.Content>
    </Tabs.Root><footer className="investigation-footer"><span><ShieldCheck size={13}/> Graph v{current.graph_version} · profile v1</span><span>Event sequence {current.latest_sequence}</span></footer>
   </>}</section>}
   </div></>}
   <footer className="page-footer"><span>RepoReaper <span className="subtle">/</span> architecture lab</span><span>Nothing published. Every conclusion stays reviewable.</span></footer>
  </main></div>
 </div></MotionConfig>;
}
