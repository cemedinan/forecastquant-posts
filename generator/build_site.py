#!/usr/bin/env python3
"""Regenera index.html unificado (Poster + posts propios de Venn).
Uso: python3 build_site.py [data.json o URL] [repo_dir]
"""
import json,sys,os,html,re,urllib.request,urllib.parse,datetime,zoneinfo
ST=os.path.dirname(os.path.abspath(__file__))
src=sys.argv[1] if len(sys.argv)>1 else 'https://cemedinan.github.io/x-virality-board/data.json'
repo=sys.argv[2] if len(sys.argv)>2 else '/workspace/site'
data=json.load(urllib.request.urlopen(src)) if src.startswith('http') else json.load(open(src))
_PA=f'{ST}/poster_archive.json'
if os.path.exists(_PA):
    _u={(h.get('status_url') or h.get('url')) for h in data['hits']}
    data['hits']+= [h for h in json.load(open(_PA)) if (h.get('status_url') or h.get('url')) not in _u]
for _h in data['hits']:
    _v=_h.get('viral') or {}
    if _v.get('hook_options'): _v['hook_options']=[x.get('hook','') if isinstance(x,dict) else x for x in _v['hook_options']]
imap=json.load(open(f'{ST}/image_map.json'));own=json.load(open(f'{ST}/own_posts.json'))
E_=lambda s:html.escape(s or '')
CTA=re.compile(r'\b(save|repost|follow|bookmark|retweet|share)\b',re.I)
def cta(t,kind):
    last=(t or '').strip().split('\n')[-1]
    if CTA.search(last): return ''
    return 'CTA sugerida: "Follow for more charts like this." o "Repost if useful."' if kind=='quote' else 'CTA sugerida: "Save this for later." o "Repost if useful."'
n=[0]
Q=lambda t:urllib.parse.quote(t,safe='')
def xlinks(text,kind,ref,img,lab2=None):
    base='https://x.com/intent/post?text='
    if kind=='quote':
        if not ref: return ''
        h=base+Q(text.rstrip()+'\n'+ref);lab='Citar en X'
    elif kind=='reply':
        m=re.search(r'/status/(\d+)',ref or '')
        if not m: return ''
        h=base+Q(text)+'&in_reply_to='+m.group(1);lab='Responder en X'
    else: h=base+Q(text);lab='Abrir en X'
    if lab2: lab=lab2
    return f'<a class="xb" data-k="{kind}" href="{E_(h)}" target="_blank" rel="noopener">{lab}</a>'
def block(label,text,kind,note='',ref='',img='',cx=None):
    if not text: return ''
    n[0]+=1;i=f'b{n[0]}';c=('CTA sugerida: "'+cx+'"' if cx else cta(text,kind)) if kind!='reply' else ''
    L=len(text)+(24 if kind=='quote' else 0)
    sh=''
    m_=re.search(r'"([^"]+)"',c or '')
    if m_:
        tc=text.rstrip()+'\n\n'+m_.group(1)
        sh=xlinks(tc,kind,ref,img,lab2={'quote':'Citar en X + CTA','reply':'Responder en X + CTA'}.get(kind,'Abrir en X + CTA'))
        L2=len(tc)+(24 if kind=='quote' else 0)
        if sh and L2>280: sh+=f'<span class="l280">+CTA: {L2} caracteres</span>'
    return (f'<div class="blk"><div class="bh"><span>{label}</span><div class="bb"><button onclick="cp(this,\'{i}\')">Copiar texto</button>{xlinks(text,kind,ref,img)}{sh}</div></div>'
            +(f'<div class="l280">más de 280 caracteres ({L})</div>' if L>280 else '')
            +f'<pre id="{i}">{E_(text)}</pre>'+(f'<div class="cta">{E_(c)}</div>' if c else '')+(f'<div class="note">{E_(note)}</div>' if note else '')+'</div>')
def fmtd(s):
    try: return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(zoneinfo.ZoneInfo('America/Santiago')).strftime('%d-%m-%Y %H:%M')
    except Exception: return ''
cards=[];skipped=[];processed=[];_tail=[]
for h in data['hits']:
    url=h.get('status_url') or h.get('url') or ''
    processed.append(url);m=imap.get(url,{})
    cards.append(dict(key=url,handle=h['handle'],views=h.get('views',0),views_label=h.get('views_label',''),date=fmtd(h.get('created_at','')),url=url,why=h.get('why_chosen',''),
      image=m.get('image'),origin=m.get('origin'),pending=m.get('pending') or ('' if m.get('image') else 'gráfico pendiente'),
      new=bool(h.get('is_new')),hl=bool(h.get('highlight')),post=h.get('draft_en'),quote=h.get('draft_quote_en'),reply=h.get('reply_angle'),video=h.get('video_tip'),hook=h.get('hook') or h.get('text',''),weak=('⚠️ Fuera de nicho: puente propio.' if h.get('off_niche') else '')+('⚠️ Contenido del post ilegible: no afirmar qué muestra.' if h.get('content_unreadable') else '')))
cards.sort(key=lambda c:(not c['hl'],-c['views']))
_SP=f'{ST}/poster_select.json';_hv={(h.get('status_url') or h.get('url') or ''):h for h in data['hits']}
if os.path.exists(_SP):
    _sel=json.load(open(_SP))
    if _sel.get('updated')==data.get('updated'):
        _keep=[]
        for c in cards:
            if c['url'] in _sel['show']: _keep.append(c)
            else: c['weak']=(c.get('weak','')+' Débil en filtro viral: '+_sel.get('reason','')).strip();_tail.append(c)
        _keep.sort(key=lambda c:_sel['show'].index(c['url']))
        for c in _keep:
            v=_hv[c['url']].get('viral') or {}
            if v.get('optimized_version'):
                c['post']=v['optimized_version'];fl=c['post'].split('\n')[0];ho=v.get('hook_options',[])
                b=next((x for x in ho if fl.startswith(x.rstrip('.')[:25])),ho[0] if ho else '')
                c['hooks']=['★ '+x if x==b else x for x in ho];c['why']=v.get('why_it_worked',c['why'])
                if v.get('visual_or_number'): c['vnote']=v['visual_or_number']
            c['vw']='Verificar antes de publicar: cifras reportadas por la cuenta de origen.'+(' '+_sel['warn'][c['url']] if c['url'] in _sel.get('warn',{}) else '')
            c['views_label']=(c['views_label']+' · ' if c['views_label'] else '')+'Mejor hora: lunes 2-nov 9:00–11:00 Chile';c['new']=True
        cards=_keep
for o in own:
    if o['url'] in processed: continue
    cards.append(dict(key=o['id'],handle=o['handle'],views=0,views_label='',date=fmtd(o.get('created_at','')),url=o['url'],why=o.get('why',''),image=o['image'],origin='venn_own',pending='',new=False,hl=False,post=o['text'],quote='',reply='',video='',hook=o['title']))
cr=json.load(open(f'{ST}/crash_posts.json')) if os.path.exists(f'{ST}/crash_posts.json') else None
pre=[]
if cr:
    for o in cr['posts']: pre.append(dict(key=o['id'],handle='idea propia',views=0,views_label='',date='29-10-2026',url='',why=o.get('why',''),image=o['image'] or None,origin='venn_own',pending='',new=True,hl=False,post=o['text'],quote='',reply='',video='',hook=o['title'],cx=o['cta'],sec=cr['section'] if o is cr['posts'][0] else '',warn=cr['warning'] if o is cr['posts'][0] else ''))
    for o in cr['memes']: pre.append(dict(key=o['id'],handle='Comedian (meme)',views=0,views_label='',date='29-10-2026',url='',why=o.get('why',''),image=o['image'],origin='comedian',pending='',new=True,hl=False,post=o['text'],quote='',reply='',video='',hook='',cx=o['cta'],sec=cr['memes_section'] if o is cr['memes'][0] else '',warn=cr.get('memes_note','') if o is cr['memes'][0] else ''))
# TrendScout: incremental store (ids estables ts-<id>; nunca duplica; descartes por localStorage)
TSP=f'{ST}/ts_store.json';tss=json.load(open(TSP)) if os.path.exists(TSP) else {}
try:
    for it in json.load(open('/workspace/trendscout_data.json')).get('items',[]):
        if it.get('off_niche'): continue
        if it['id'] in tss:
            if it.get('draft_en')!=tss[it['id']].get('draft_en'): tss[it['id']].update({k:v for k,v in it.items() if k!='image_path'});tss[it['id']]['text_ext']=it.get('draft_en');tss[it['id']]['hooks_show']=it.get('hooks')
            continue
        r=dict(it);r.update(image=None,theme='',text_ext=it.get('draft_en'),pending='gráfico pendiente (TrendScout: generar 4:5 con visual_brief)');tss[it['id']]=r
    json.dump(tss,open(TSP,'w'),ensure_ascii=False,indent=1)
except FileNotFoundError: pass
tsc=[]
for it in sorted(tss.values(),key=lambda x:(x.get('priority',9),x.get('date',''))):
    _dst=_tail if it.get('hidden') else tsc
    _dst.append(dict(key='ts-'+it['id'],handle='TrendScout',views=0,views_label=f"Mejor hora: {it.get('best_time','')}",date=fmtd(it.get('date','')),url=it.get('source_url',''),why=it.get('potential',''),image=it.get('image'),origin='trendscout',pending=it.get('pending','') if not it.get('image') else '',new=False,hl=False,post=it.get('text_ext') or it.get('draft_en'),quote=it.get('draft_quote_en') or '',reply=it.get('reply_angle') or '',video='',hook=it.get('topic',''),cx=(it.get('cta') or '').split(' / ')[0] or None,sec='TrendScout (investigación diaria)' if (not tsc and not it.get('hidden')) else '',weak=('Débil en filtro viral: '+it['hidden']) if it.get('hidden') else '',warn='',hooks=it.get('hooks_show') or [],vw=it.get('verify','')))
_rest0=cards[0] if cards else None;_orig=set(map(id,cards))
_mk=[]
_MS=f'{ST}/memes_store.json'
if os.path.exists(_MS):
    for dt,g in sorted(json.load(open(_MS)).items(),reverse=True):
        mm={m['id']:m for m in g['memes']}
        for k,i in enumerate(g['order']):
            m=mm[i];_vn=g.get('by')=='venn';_mk.append(dict(key=m['id'],handle='Venn (meme)' if _vn else 'Comedian (meme)',views=0,views_label=g.get('best','Mejor hora: lunes 2-nov 9:00–11:00 Chile')+' · '+m['viral'],date=dt,url='',why=m['title'],image=m['image'],origin='venn_meme' if _vn else 'comedian',pending='',new=True,hl=False,post=m['text'],quote='',reply='',video='',hook='',cx=m['cta'],alt=m['alt'],hooks=m['hooks'],vw='Hechos a verificar: '+m['verify'],sec=g['section'] if k==0 else '',warn=g.get('note','') if k==0 else ''))
cards=_mk+pre+tsc+cards
_TP=f'{ST}/today.json'
if os.path.exists(_TP):
    _t=json.load(open(_TP));_by={c['key']:c for c in cards};_top=[_by[k] for k in _t['keys'] if k in _by]
    if _top:
        for c in _top: c['sec']='';c['warn']=''
        _top[0]['sec']=_t['title'];_top[0]['warn']=_t.get('note','')
        _ids=set(map(id,_top));_others=[c for c in cards if id(c) not in _ids]
        for c in _others:
            if c.get('origin') in ('comedian','venn_meme') and c['key'].startswith('meme-2026'): c['sec']=''
        cards=_top+_others;_rest0=next((c for c in _others if id(c) in _orig),None)
_H3=json.load(open(f'{ST}/hooks3.json')) if os.path.exists(f'{ST}/hooks3.json') else {}
_tids=set(map(id,_tail));cards=[c for c in cards if id(c) not in _tids]
if _tail:
    _tail[0]['sec']='Ideas con menor potencial (al final, marcadas; nunca se omiten)';_tail[0]['warn']='Débiles para el filtro viral o fuera de nicho. Revisar ⚠️ antes de publicar.'
    cards=cards+_tail
for c in cards:
    h=_H3.get(c['key'])
    if not h and c.get('hooks') and c.get('post'):
        hs=[x.replace('★ ','') for x in c['hooks']];st=next((i for i,x in enumerate(c['hooks']) if x.startswith('★')),0)
        o=[hs[st]]+[x for i,x in enumerate(hs) if i!=st][:2]
        if len(o)==3: h=dict(hooks=o,star=0,body=c['post'].split('\n\n',1)[-1] if '\n\n' in c['post'] else '\n'.join(c['post'].split('\n')[1:]))
    c['h3']=h
    if h and h.get('warn'): c['vw']=((c.get('vw') or '')+' '+h['warn']).strip()
out=[]
for c in cards:
    if c.get('sec'): out.append(f'<h2 class="sec">{E_(c["sec"])}</h2>'+(f'<div class="warn">{E_(c["warn"])}</div>' if c.get('warn') else ''))
    if c is _rest0 and pre: out.append('<h2 class="sec">Resto de recomendaciones</h2>')
    gr='1' if c['image'] else '0';nw='1' if c['new'] else '0'
    ref=(f'<a class="ref" href="{E_(c["url"])}" target="_blank" rel="noopener">Ver post de referencia ↗</a>' if c['url'] else
         f'<span class="noref">{"Idea propia / sin enlace" if c["handle"]=="idea propia" else "Sin enlace de referencia"}</span>')
    lab={'poster':'Visual de Poster','venn':'Visual sugerido por Venn','venn_own':'Gráfico de Venn (post propio)','comedian':'Meme de Comedian','venn_meme':'Memes (Venn)','trendscout':'Visual de Venn (brief de TrendScout)'}.get(c['origin'],'')
    _im=c.get('image') or ''
    if lab and _im.endswith('_dia_v.png'): lab+=' · tema día'
    elif lab and _im.endswith('_v.png'): lab+=' · tema noche'
    img=(f'<a href="images/{c["image"]}" target="_blank"><img src="images/{c["image"]}" alt="" loading="lazy"></a><div class="il"><span class="lab">{lab}</span><span><a class="dl" href="images/{c["image"]}" download>Descargar imagen</a>{(' · <a class=\"hz\" href=\"images/'+c["image"].replace('_dia_v.png','.png').replace('_noche_v.png','.png').replace('_v.png','.png')+'\" target=\"_blank\">Ver versión horizontal</a>') if c["image"].endswith('_v.png') and os.path.exists(os.path.join(repo,'images',c["image"].replace('_dia_v.png','.png').replace('_noche_v.png','.png').replace('_v.png','.png'))) else ''}</span></div>'
         if c['image'] else '')
    tags=('<span class="pill">Destacado</span>' if c['hl'] else '')+('<span class="pill new">Nuevo</span>' if c['new'] else '')
    out.append(f'<article class="card" id="{E_(re.sub(r"\\W","",c["key"])[-24:])}" data-id="{E_(c["key"])}" data-g="{gr}" data-n="{nw}"><div class="ch"><div><b>{E_(c["handle"])}</b> {tags}<div class="sm">{E_(c["views_label"])}{" · " if c["views_label"] and c["date"] else ""}{c["date"]}</div></div>{ref}</div>'
      +(f'<div class="hook">{E_(c["hook"][:220])}</div>' if c['hook'] else '')+(f'<div class="why"><b>Por qué:</b> {E_(c["why"])}</div>' if c['why'] else '')+(f'<div class="warn">⚠️ {E_(c["weak"])}</div>' if c.get('weak') else '')+(f'<div class="warn">⚠️ {E_(c["vw"])}</div>' if c.get('vw') else '')+(f'<div class="why"><b>Dato/visual:</b> {E_(c["vnote"])}</div>' if c.get('vnote') else '')+img
      +(''.join(block(('★ ' if i==c['h3'].get('star',0) else '')+f'Hook {i+1} · post armado',x+'\n\n'+c['h3']['body'],'post',img=c['image'] or '',cx=c['h3'].get('cta') or c.get('cx')) for i,x in enumerate(c['h3']['hooks'][:3])) if c.get('h3') else block('Post nuevo',c['post'],'post',img=c['image'] or '',cx=c.get('cx')))+block('Alternativa',c.get('alt',''),'post')+block('Quote post',c['quote'],'quote',ref=c['url'] if c['origin'] not in ('venn_own','comedian') else '',img=c['image'] or '')+block('Reply / comentario — ángulo',c['reply'],'reply',note='Es un ángulo, no un texto final: edítalo en X antes de responder.',ref=c['url'] if c['origin'] not in ('venn_own','comedian') else '')
      +(f'<div class="vt">🎬 Idea de video (opcional): {E_(c["video"])}</div>' if c['video'] else '')+'<div class="dz"><button class="dx" onclick="dis(this.closest(\'.card\'))">✕ Descartar</button></div></article>')
now=datetime.datetime.now(zoneinfo.ZoneInfo('America/Santiago')).strftime('%d-%m-%Y %H:%M')
sk=''.join(f'<li>{E_(a)} — {b}{f" · <a href={chr(34)}{E_(u)}{chr(34)} target=_blank>post</a>" if u else ""}</li>' for a,b,u in skipped)
css=""".sec{color:#C6E427;font-size:20px;margin:22px 4px 4px}.warn{border:1px solid #C6E427;border-radius:10px;padding:10px;font-size:13px;color:#fff;margin:6px 0}
*{box-sizing:border-box}body{margin:0;background:#0B0D26;color:#fff;font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.top{position:sticky;top:0;z-index:10;background:#0B0D26;border-bottom:1px solid #2a2f5a}.tb{max-width:900px;margin:auto;padding:8px 16px;display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}.tb b{font-size:15px}.tb span{color:#B8BCCB;font-size:12px}#rf{background:#C6E427;color:#0B0D26;border:0;border-radius:8px;padding:6px 12px;font-weight:700;cursor:pointer;font-size:14px}
header{display:flex;gap:14px;align-items:center;padding:18px 16px;max-width:900px;margin:auto}header img{width:56px;height:56px;border-radius:10px}h1{margin:0;font-size:24px}header p{margin:4px 0;color:#B8BCCB;font-size:14px}
.chips{max-width:900px;margin:0 auto 6px;padding:0 16px;display:flex;gap:8px;flex-wrap:wrap}.chips button{background:transparent;color:#C6E427;border:1px solid #C6E427;border-radius:20px;padding:6px 14px;font-size:14px;cursor:pointer}.chips button.on{background:#C6E427;color:#0B0D26}
main{max-width:900px;margin:auto;padding:8px 12px 40px}.card{background:#141838;border:1px solid #2a2f5a;border-radius:14px;padding:14px;margin:14px 0}
.ch{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}.sm{color:#B8BCCB;font-size:13px}.ref{background:#C6E427;color:#0B0D26;font-weight:700;padding:8px 12px;border-radius:8px;text-decoration:none;white-space:nowrap}.noref{color:#B8BCCB;font-size:13px;border:1px dashed #555;padding:6px 10px;border-radius:8px}
.pill{background:#2a2f5a;color:#C6E427;border-radius:10px;padding:1px 8px;font-size:12px;margin-left:4px}.pill.new{background:#C6E427;color:#0B0D26}
.hook{color:#B8BCCB;font-size:13px;margin:8px 0;font-style:italic}.why{font-size:14px;margin:6px 0 10px}.why b{color:#C6E427}
.card img{width:100%;max-height:560px;object-fit:contain;background:transparent;border-radius:10px;display:block;margin:auto;cursor:zoom-in}@media(max-width:640px){.card img{max-height:none}}.hz{color:#B8BCCB}.il{display:flex;justify-content:space-between;font-size:13px;margin:6px 0 4px}.lab{color:#C6E427}.dl{color:#fff}
.pend{border:1px dashed #C6E427;color:#C6E427;border-radius:10px;padding:14px;font-size:14px;margin:6px 0}
.blk{border-left:3px solid #C6E427;margin:12px 0 0;padding:0 0 0 10px}.bh{display:flex;justify-content:space-between;align-items:center}.bh span{font-weight:700;color:#C6E427}
.bh button{background:#C6E427;color:#0B0D26;border:0;border-radius:8px;padding:6px 12px;font-weight:700;cursor:pointer}pre{white-space:pre-wrap;font:inherit;margin:6px 0;background:#0B0D26;padding:10px;border-radius:8px}
.bb{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.bh{gap:8px;flex-wrap:wrap}.xb,.sh{background:#0B0D26;color:#C6E427;border:1px solid #C6E427!important;border-radius:8px;padding:8px 12px;font-weight:700;text-decoration:none;font-size:14px;min-height:40px;display:inline-flex;align-items:center;cursor:pointer}.bh button{min-height:40px}.l280{color:#B8BCCB;font-size:12px;text-align:right}.note{color:#B8BCCB;font-size:12px}
.cta{color:#B8BCCB;font-size:13px}.vt{color:#B8BCCB;font-size:13px;margin-top:10px}details{color:#B8BCCB;font-size:13px;max-width:900px;margin:0 auto 30px;padding:0 16px}details a{color:#C6E427}
.card{position:relative;touch-action:pan-y;will-change:transform}.card.dis,.dhide .card.dis{display:none!important}.dz{text-align:right;margin-top:10px}.dx{background:transparent;color:#B8BCCB;border:1px solid #444a7a;border-radius:8px;padding:4px 10px;font-size:13px;cursor:pointer}
.swl{position:absolute;right:16px;top:50%;transform:translateY(-50%);color:#ff6b6b;font-weight:700;pointer-events:none}.cardwrap{position:relative}
.hint{max-width:900px;margin:0 auto 4px;padding:0 16px;color:#B8BCCB;font-size:12px}.hint a{color:#C6E427;cursor:pointer}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#C6E427;color:#0B0D26;padding:10px 16px;border-radius:10px;font-weight:700;display:none;z-index:20}#toast a{color:#0B0D26;text-decoration:underline;margin-left:8px;cursor:pointer}
#dl{max-width:900px;margin:0 auto 10px;padding:0 16px;display:none}#dl li{margin:4px 0;color:#B8BCCB;font-size:13px}#dl button{background:transparent;color:#C6E427;border:1px solid #C6E427;border-radius:8px;padding:2px 8px;margin-left:6px;cursor:pointer}"""
js="""function xdeep(h){var u=new URL(h);var t=u.searchParams.get("text")||"";var d="twitter://post?message="+encodeURIComponent(t);var r=u.searchParams.get("in_reply_to");if(r)d+="&in_reply_to_status_id="+r;return d}
document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a.xb");if(!a)return;var ios=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform=="MacIntel"&&navigator.maxTouchPoints>1);if(!ios)return;e.preventDefault();var w=a.href,tm;function cl(){if(document.hidden){clearTimeout(tm);document.removeEventListener("visibilitychange",cl)}}document.addEventListener("visibilitychange",cl);tm=setTimeout(function(){document.removeEventListener("visibilitychange",cl);if(!document.hidden)location.href=w},1500);location.href=xdeep(w)});
function rf(b){b.textContent="Actualizando…";b.disabled=true;var c=document.querySelector(".chips button.on"),k=c?c.dataset.k:"all";var u=location.pathname+"?v="+Date.now()+(k&&k!="all"?"#f="+k:"");setTimeout(function(){location.replace(u)},300)}
document.addEventListener("DOMContentLoaded",function(){var m=location.hash.match(/f=([a-z]+)/);if(m){var b=document.querySelector('.chips button[data-k="'+m[1]+'"]');if(b)f(m[1],b)}});
function cp(b,id){var t=document.getElementById(id).textContent;function ok(){b.textContent="Copiado";setTimeout(function(){b.textContent="Copiar texto"},2000)}function fb(){var e=document.createElement("textarea");e.value=t;e.style.position="fixed";e.style.opacity="0";document.body.appendChild(e);e.select();try{document.execCommand("copy")}catch(x){}document.body.removeChild(e);ok()}if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,fb)}else fb()}
var DK="fq_dismissed_v1";function ld(){try{return JSON.parse(localStorage.getItem(DK)||"[]")}catch(e){return []}}function sv(a){try{localStorage.setItem(DK,JSON.stringify(a))}catch(e){}}
var lastD=null,tT=null;function cards(){return Array.prototype.slice.call(document.querySelectorAll(".card"))}
function apply(){var d=ld();cards().forEach(function(c){c.classList.toggle("dis",d.indexOf(c.dataset.id)>=0);c.style.transform="";c.style.opacity=""});var v=cards().filter(function(c){return !c.classList.contains("dis")}).length;var e=document.getElementById("cnt");if(e)e.textContent=v;var n=document.getElementById("dn");if(n)n.textContent=d.length;rl()}
function rl(){var l=document.getElementById("dll");if(!l)return;var d=ld();l.innerHTML="";d.forEach(function(id){var c=cards().filter(function(x){return x.dataset.id==id})[0];var li=document.createElement("li");var b=c?c.querySelector(".ch b"):null;li.textContent=(b?b.textContent+" — ":"")+id;var r=document.createElement("button");r.textContent="Restaurar";r.onclick=function(){res(id)};li.appendChild(r);l.appendChild(li)})}
function dis(c){if(!c)return;var d=ld(),id=c.dataset.id;if(d.indexOf(id)<0)d.push(id);sv(d);lastD=id;apply();var t=document.getElementById("toast");if(t){t.style.display="block";clearTimeout(tT);tT=setTimeout(function(){t.style.display="none"},6000)}}
function undo(){if(lastD)res(lastD);lastD=null;var t=document.getElementById("toast");if(t)t.style.display="none"}
function res(id){sv(ld().filter(function(x){return x!=id}));apply()}function resAll(){sv([]);apply()}
function tgl(){var l=document.getElementById("dl");l.style.display=l.style.display=="block"?"none":"block"}
function cpd(){var t=JSON.stringify(ld());var e=document.createElement("textarea");e.value=t;document.body.appendChild(e);e.select();try{document.execCommand("copy")}catch(x){}document.body.removeChild(e);if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(t).catch(function(){});alert("Lista copiada ("+ld().length+")")}
function psd(){var t=prompt("Pega la lista de descartadas (JSON):");if(!t)return;try{var a=JSON.parse(t);if(Array.isArray(a)){var d=ld();a.forEach(function(x){if(typeof x=="string"&&d.indexOf(x)<0)d.push(x)});sv(d);apply()}}catch(e){alert("Lista no válida")}}
function sw(c){var x0=0,y0=0,dx=0,on=false,lock=0,pid=null;
c.addEventListener("pointerdown",function(e){if(e.pointerType=="mouse"&&e.button!==0)return;if(e.target.closest("button,pre,textarea,input"))return;x0=e.clientX;y0=e.clientY;dx=0;on=true;lock=0;pid=e.pointerId});
c.addEventListener("pointermove",function(e){if(!on||e.pointerId!==pid)return;var mx=e.clientX-x0,my=e.clientY-y0;if(!lock){if(Math.abs(mx)<8&&Math.abs(my)<8)return;lock=Math.abs(mx)>Math.abs(my)*1.5?1:2;if(lock==1){c._sw=true;try{c.setPointerCapture(pid)}catch(z){}c.style.transition="none"}}if(lock!=1)return;dx=Math.min(0,mx);c.style.transform="translateX("+dx+"px)";c.style.opacity=String(Math.max(.25,1+dx/400));c.style.boxShadow=dx<-90?"inset -6px 0 0 #ff6b6b":"inset -6px 0 0 #C6E427"});
function end(){if(!on)return;on=false;c.style.transition="transform .2s,opacity .2s";c.style.boxShadow="";if(lock==1)setTimeout(function(){c._sw=false},50);if(lock==1&&dx<-90){c.style.transform="translateX(-120%)";c.style.opacity="0";setTimeout(function(){dis(c);c.style.transition=""},200)}else{c.style.transform="";c.style.opacity=""}lock=0}
c.addEventListener("click",function(e){if(c._sw){e.preventDefault();e.stopPropagation();c._sw=false}},true);c.addEventListener("dragstart",function(e){if(on)e.preventDefault()});c.addEventListener("pointerup",end);c.addEventListener("pointercancel",end)}
document.addEventListener("DOMContentLoaded",function(){cards().forEach(sw);apply();var s=document.getElementById("predis");if(s)s.remove()});
function f(k,b){document.querySelectorAll('.chips button').forEach(function(x){x.classList.remove('on')});b.classList.add('on');document.querySelectorAll('.card').forEach(function(c){c.style.display=(k=='all'||(k=='g'&&c.dataset.g=='1')||(k=='n'&&c.dataset.n=='1'))?'':'none'})}"""
page=f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0"><title>Recomendaciones para X</title><style>{css}</style><script>try{{var _d=JSON.parse(localStorage.getItem("fq_dismissed_v1")||"[]");if(_d.length&&window.CSS&&CSS.escape)document.write('<style id="predis">'+_d.map(function(x){{return '.card[data-id="'+CSS.escape(x)+'"]'}}).join(",")+'{{display:none!important}}</style>')}}catch(e){{}}</script></head><body>
<div class="top"><div class="tb"><b>Recomendaciones para X</b><span>Última actualización: {now} (hora Chile)</span><button id="rf" onclick="rf(this)">&#x21bb; Actualizar</button></div></div>
<header><img src="images/logo.jpg" alt="logo"><div><h1>Recomendaciones para X</h1><p>Actualizado: {now} (hora Chile) · <span id="cnt">{len(cards)}</span> de {len(cards)} tarjetas visibles</p><p>Borradores para revisar: nada se publica solo. Mejor horario: 9:00 a 11:00 hora Chile, en días de semana.</p><p>Orden: destacados de Poster primero, luego por vistas; al final, los posts propios con gráfico.</p></div></header>
<div class="chips"><button class="on" data-k="all" onclick="f('all',this)">Todos</button><button data-k="g" onclick="f('g',this)">Con gráfico</button><button data-k="n" onclick="f('n',this)">Nuevos</button></div>
<div class="hint">Desliza una tarjeta a la izquierda para descartarla (o usa ✕ Descartar). · <a onclick="tgl()">Descartadas (<span id="dn">0</span>)</a></div>
<div id="dl"><ul id="dll"></ul><button onclick="resAll()">Restaurar todas</button> <button onclick="cpd()">Copiar lista de descartadas</button> <button onclick="psd()">Pegar lista</button></div>
<div id="toast">Tarjeta descartada · <a onclick="undo()">Deshacer</a></div>
<main>{''.join(out)}</main><script>{js}</script></body></html>"""
# Conversaciones de interés. Ventana fija de 7200s sobre created_at del post
# original. La página completa queda en <repo>/conversaciones/index.html;
# index.html solo recibe el enlace. Un rebuild no borra esa página.
# No publica nada en X. Sync: powerlaw_conversations.py junto a este archivo.
import powerlaw_conversations as _pl
page=_pl.inject_into_page(page, ST, repo_dir=repo)
open(os.path.join(repo,'index.html'),'w').write(page)
pp=f'{ST}/poster_processed.json';old=json.load(open(pp)) if os.path.exists(pp) else []
json.dump(sorted(set(old)|set(processed)),open(pp,'w'),indent=1)
miss=[c['image'] for c in cards if c['image'] and not os.path.exists(os.path.join(repo,'images',c['image']))]
print('cards',len(cards),'skipped',len(skipped),'missing images',miss)
