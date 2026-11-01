"use client";

import { useEffect, useRef, useState } from 'react';
import { MEDICAL, OFF_TOPIC, mentions, products, ruleReply } from './hafiller-data';
import { strings, useLang, type Lang } from './hafiller-i18n';
import './hafiller-bot.css';

type Message = { role: 'user' | 'assistant'; content: string };
type KnowledgeProduct = { name:string; content:string; source:string };
type Progress = { id: number; done: boolean };
const welcomes = Object.values(strings).map(s=>s.welcome);
// 预计进度只按等待时间推进，不对应后端真实步骤：各阶段开始的秒数
const STAGE_AT = [0, 3, 7, 13];
const SLOW_AFTER = 25;
function Robot({ small = false }: { small?: boolean }) {
  return <svg width={small ? 28 : 38} height={small ? 28 : 38} viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M24 8V4" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/><circle cx="24" cy="4" r="3" fill="#b8edda"/><rect x="7" y="12" width="34" height="28" rx="12" fill="currentColor"/><rect x="12" y="18" width="24" height="13" rx="6" fill="#435b50"/><circle cx="19" cy="24" r="2.5" fill="#c9f6e1"/><circle cx="29" cy="24" r="2.5" fill="#c9f6e1"/><path d="M21 35h6M3 23v7m42-7v7" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/></svg>;
}
function AiProgress({ done, lang, onSlow }: { done: boolean; lang: Lang; onSlow: () => void }) {
  const t = strings[lang];
  const start = useRef(Date.now());
  const [elapsed,setElapsed] = useState(0);
  useEffect(()=>{
    if (done) return;
    const timer = window.setInterval(()=>setElapsed((Date.now()-start.current)/1000),250);
    return ()=>window.clearInterval(timer);
  },[done]);
  const slow = !done && elapsed >= SLOW_AFTER;
  useEffect(()=>{ if(slow) onSlow(); },[slow]);
  // 渐近 90%：约 8 秒过半，之后越来越慢；收到回复才到 100%
  const percent = done ? 100 : Math.round(90*(1-Math.exp(-elapsed/12)));
  const stage = t.stages[STAGE_AT.filter(s=>elapsed>=s).length-1];
  return <div className="hf-progress" role="progressbar" aria-label={t.progressTitle} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${t.progressTitle} ${percent}% · ${stage}`}>
    <div className="hf-progress-label"><span>{t.progressTitle} · {stage}</span><span>{percent}%</span></div>
    <div className="hf-progress-track"><div className="hf-progress-bar" style={{width:`${percent}%`}}/></div>
    {slow && <p className="hf-progress-hint">{t.slowHint}</p>}
  </div>;
}
function errorText(error: unknown, lang: Lang) {
  const t = strings[lang];
  if (error instanceof DOMException && error.name === 'TimeoutError') return t.errTimeout;
  if (error instanceof TypeError) return t.errNetwork;  // fetch 断网时浏览器给的英文原文不直接显示
  if (error instanceof Error && error.message) return error.message;
  return t.errNetwork;
}
export default function HafillerBot() {
  const lang = useLang();
  const t = strings[lang];
  const [open,setOpen] = useState(false);
  const [messages,setMessages] = useState<Message[]>(()=>[{role:'assistant',content:strings[lang].welcome}]);
  const [input,setInput] = useState('');
  const [mode,setMode] = useState('rules');
  const [selected,setSelected] = useState<string[]>(['Fine Lines']);
  const [knowledge,setKnowledge] = useState<KnowledgeProduct[]>([]);
  const [knowledgeError,setKnowledgeError] = useState(false);
  const allProducts = [...products, ...knowledge.filter(p=>!products.some(base=>base.name.toLowerCase()===p.name.toLowerCase()))];
  useEffect(()=>{
    if (!open) return;
    let active = true;
    fetch('/api/product-knowledge',{cache:'no-store'}).then(async response=>{
      if (!response.ok) throw new Error();
      const data = await response.json();
      if(active) { setKnowledge(data.products); setKnowledgeError(false); }
    }).catch(()=>{if(active) setKnowledgeError(true);});
    return ()=>{active=false;};
  },[open]);
  // 切语言时已有对话不改；只有欢迎语时换成新语言的欢迎语
  useEffect(()=>{
    setMessages(items=>items.length===1 && welcomes.includes(items[0].content) && items[0].content!==strings[lang].welcome ? [{role:'assistant',content:strings[lang].welcome}] : items);
  },[lang]);
  const [busy,setBusy] = useState(false);
  const [progress,setProgress] = useState<Progress | null>(null);
  const [leadOpen,setLeadOpen] = useState(false);
  const [notice,setNotice] = useState<'' | 'copied' | 'copyFailed'>('');
  const end = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const scrollEnd = ()=>end.current?.scrollIntoView({behavior:'smooth',block:'nearest'});
  useEffect(()=>{ if(open) scrollEnd(); },[messages,busy,progress,open]);
  useEffect(()=>{ if(open) inputRef.current?.focus(); },[open]);
  useEffect(()=>{ if(!open) return; const close=(e: KeyboardEvent)=>{if(e.key==='Escape') setOpen(false);}; document.addEventListener('keydown',close); return ()=>document.removeEventListener('keydown',close); },[open]);
  async function send(value: string) {
    if(!value.trim() || pending.current) return;
    pending.current = true;
    const next: Message[] = [...messages,{role:'user',content:value.trim().slice(0,2000)}];
    const ai = mode === 'ai';
    const id = Date.now();
    setMessages(next); setInput(''); setBusy(true); setNotice('');
    if(ai) setProgress({id,done:false});
    let content: string;
    try {
      if(ai) {
        const aiMessages = next.slice(-12).map((message,index,array)=>index===array.length-1 ? {...message,content:`${t.selectedPrefix}${selected.join(t.join)}\n${message.content}`} : message);
        const response = await fetch('/api/hafiller-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:aiMessages}),signal:AbortSignal.timeout(65000)});
        const data = await response.json().catch(()=>({}));
        if(!response.ok || typeof data.reply !== 'string') throw new Error(data.error || t.errAi);
        content = data.reply;
      } else {
        const text = value.toLowerCase();
        const boundary = ruleReply(value,selected[0],lang);
        const sensitive = OFF_TOPIC.test(text) || MEDICAL.test(text);
        const explicit = [...allProducts].sort((a,b)=>b.name.length-a.name.length).filter(p=>mentions(value,p.name));
        const targets = explicit.length ? explicit.filter(p=>!explicit.some(other=>other.name!==p.name && other.name.toLowerCase().includes(p.name.toLowerCase()))) .map(p=>p.name) : selected;
        content = sensitive ? boundary : targets.map(name=>{
          const item = knowledge.find(p=>p.name.toLowerCase()===name.toLowerCase());
          return item ? `${item.name}${t.imported}\n${item.content}\n${t.source}${item.source || t.importedSource}\n\n${t.importedNote}` : ruleReply(value.replace(new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'ig'),''),name,lang);
        }).filter((reply,index,array)=>array.indexOf(reply)===index).join('\n\n');
      }
    } catch(error) { content = errorText(error,lang); }
    setMessages([...next,{role:'assistant',content}]); setBusy(false); pending.current = false;
    if(ai) {
      // 先走到 100% 再消失；期间若已开始下一轮，id 不同，不影响新进度条
      setProgress(p=>p && p.id===id ? {id,done:true} : p);
      window.setTimeout(()=>setProgress(p=>p && p.id===id ? null : p),450);
    }
  }
  function collect(form: HTMLFormElement) {
    const data = new FormData(form);
    const field = (name: string) => String(data.get(name) ?? '');
    const summary = t.summary({products:selected.join(t.join),country:field('country'),type:field('type'),quantity:field('quantity'),delivery:field('delivery'),contact:field('contact')});
    setMessages(items=>[...items,{role:'assistant',content:summary}]); setLeadOpen(false);
  }
  return <div className="hf-root" lang={lang==='en' ? 'en' : 'zh-CN'}>
    {open && <section className="hf-panel" aria-label={t.panel}>
      <header className="hf-header"><span className="hf-avatar"><Robot small/></span><div><strong>{t.title}</strong><p><i/> {t.subtitle}</p></div><button type="button" className="hf-close" aria-label={t.close} onClick={()=>setOpen(false)}>×</button></header>
      <div className="hf-toolbar"><div className="hf-modes" aria-label={t.modes}><button aria-pressed={mode==='rules'} onClick={()=>setMode('rules')}>{t.rules}</button><button aria-pressed={mode==='ai'} onClick={()=>setMode('ai')}>{t.ai} <span>✦</span></button></div><button className="hf-reset" disabled={busy} onClick={()=>{setMessages([{role:'assistant',content:t.welcome}]);setLeadOpen(false);setNotice('');}}>{t.reset}</button></div>
      <p className="hf-mode-note">{mode==='ai' ? t.noteAi : t.noteRules}</p>
      <div className="hf-messages" role="log" aria-live="polite" aria-relevant="additions">{messages.map((m,i)=><div key={i} className={`hf-message hf-${m.role}`}>{m.role==='assistant' && <span className="hf-mini"><Robot small/></span>}<div className="hf-bubble">{m.content}</div></div>)}{progress ? <AiProgress key={progress.id} done={progress.done} lang={lang} onSlow={scrollEnd}/> : busy && <div className="hf-thinking">{t.thinking}<span>···</span></div>}<div ref={end}/></div>
      {leadOpen ? <form className="hf-lead" onSubmit={e=>{e.preventDefault();collect(e.currentTarget);}}><div className="hf-form-title"><strong>{t.leadTitle}</strong><button type="button" onClick={()=>setLeadOpen(false)} aria-label={t.leadClose}>×</button></div><div className="hf-fields"><label>{t.country}<input name="country" required maxLength={80} placeholder={t.countryPh}/></label><label>{t.type}<select name="type">{t.types.map(type=><option key={type}>{type}</option>)}</select></label><label>{t.quantity}<input name="quantity" required maxLength={80} placeholder={t.quantityPh}/></label><label>{t.delivery}<input name="delivery" maxLength={80} placeholder={t.optional}/></label><label className="hf-full">{t.contact}<input name="contact" maxLength={160} placeholder={t.contactPh}/></label></div><p>{t.privacy}</p><button type="submit" className="hf-submit">{t.submit}</button></form> : <div className="hf-shortcuts"><div className="hf-product"><span>{t.pick}</span><strong>{t.picked(selected.length)}</strong></div><div className="hf-product-options">{allProducts.map(p=><label key={p.name}><input type="checkbox" checked={selected.includes(p.name)} onChange={()=>setSelected(items=>items.includes(p.name) ? (items.length === 1 ? items : items.filter(item=>item !== p.name)) : [...items,p.name])}/><span>{p.name}</span></label>)}</div>{knowledgeError && <p className="hf-mode-note">{t.knowledgeError}</p>}<div className="hf-chips">{t.chips.map(label=><button disabled={busy} key={label} onClick={()=>send(`${selected.join(t.join)} ${label}`)}>{label}</button>)}<button disabled={busy} onClick={()=>setLeadOpen(true)}>{t.leadChip}</button></div></div>}
      <form className="hf-composer" onSubmit={e=>{e.preventDefault();void send(input);}}><input ref={inputRef} value={input} maxLength={2000} onChange={e=>setInput(e.target.value)} placeholder={t.placeholder} aria-label={t.inputLabel}/><button type="submit" aria-label={t.sendLabel} disabled={busy||!input.trim()}>↑</button></form>
      <footer className="hf-footer"><span>{t.footer}</span><button onClick={async()=>{try{await navigator.clipboard.writeText(messages.map(m=>`${m.role==='user'?t.customer:t.agent}${lang==='en' ? ': ' : '：'}${m.content}`).join('\n\n'));setNotice('copied');}catch{setNotice('copyFailed');}}}>{notice ? t[notice] : t.copy}</button></footer>
    </section>}
    <button className={`hf-launcher ${open?'hf-is-open':''}`} aria-label={open?t.closeLabel:t.openLabel} aria-expanded={open} onClick={()=>setOpen(!open)}><Robot/>{!open&&<span>{t.launcher}<small>HAFILLER ASSISTANT</small></span>}<span className="hf-online"/></button>
  </div>;
}
