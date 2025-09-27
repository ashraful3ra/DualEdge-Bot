let R_points=[]; let symbolsCache=[]; let sio=null; let currentPage = 1;
function el(tag,attrs={},children=[]){const e=document.createElement(tag);Object.entries(attrs).forEach(([k,v])=>{if(k==='class')e.className=v;else if(k==='html')e.innerHTML=v;else e.setAttribute(k,v);});children.forEach(c=>e.appendChild(c));return e;}
function renderR(){const root=document.getElementById('r_list');root.innerHTML='';R_points.forEach((v,i)=>{const val = (v === null || isNaN(v)) ? '' : v; const inp=el('input',{class:'input',type:'number',step:'0.1',value:val, placeholder:`R${i+1}`});inp.addEventListener('input',ev=>{R_points[i]=parseFloat(ev.target.value); if(isNaN(R_points[i])) R_points[i]=null});root.appendChild(inp);});}
function renderTemplates(items){const root=document.getElementById('tpl_list');root.innerHTML='';if(!items.length){root.innerHTML='<div class="small">No templates</div>';return;}for(const t of items){const d=el('div',{class:'list-item'});d.innerHTML=`<div><div class="name">${t.name}</div><div class="small">${new Date(t.created_at*1000).toLocaleString()}</div></div><div class="row"><button class="btn" data-id="${t.id}" data-act="load"><i class="fas fa-edit"></i></button><button class="btn btn-danger" data-id="${t.id}" data-act="del"><i class="fas fa-trash-alt"></i></button></div>`;root.appendChild(d);}root.querySelectorAll('button').forEach(b=>b.addEventListener('click',async ev=>{const btn=ev.target.closest('button');const id=btn.getAttribute('data-id');const act=btn.getAttribute('data-act');if(act==='del'){if(!confirm('Delete template?'))return;await fetch('/templates/delete/'+id,{method:'POST'});loadTemplates();}else{const r=await fetch('/templates/get/'+id);const t=await r.json();loadTemplateIntoForm(t);}}));}
function loadTemplateIntoForm(t){bot_name.value=t.name;bot_symbol.value=t.symbol||'';long_on.checked=!!t.long_enabled;short_on.checked=!!t.short_enabled;long_lev.value=t.long_leverage||'';short_lev.value=t.short_leverage||'';long_amt.value=t.long_amount||'';short_amt.value=t.short_amount||'';R_points=(t.r_points||[]).filter(p => p !== null); if(R_points.length < 5) { R_points.push(...new Array(5 - R_points.length).fill(null)); } renderR();cond_sl_close.checked=!!t.cond_sl_close;cond_trailing.checked=!!t.cond_trailing;cond_close_last.checked=!!t.cond_close_last;document.getElementById('margin_mode').value = t.margin_type || 'ISOLATED';}
async function safeJson(r){const txt=await r.text();try{return JSON.parse(txt)}catch(e){return {__raw:txt, error:`HTTP ${r.status}`}}}
async function fetchSymbols(){const r=await fetch('/api/futures/symbols');const d=await safeJson(r);if(d.symbols){return d.symbols;}alert('Symbol list error: '+(d.error||d.__raw||'unknown'));return [];}
async function initSymbolSuggest(){
    symbolsCache = await fetchSymbols();
    const input = document.getElementById('bot_symbol');
    const list = document.getElementById('symbol_suggest');

    input.addEventListener('input', e => {
        updateMinNotional();
        const q = (e.target.value || '').toUpperCase();
        if (!q) {
            list.innerHTML = '';
            list.style.display = 'none';
            return;
        }
        const matches = symbolsCache.filter(s => s.startsWith(q)).slice(0, 10);
        list.innerHTML = '';
        if (matches.length) {
            list.style.display = 'block';
        } else {
            list.style.display = 'none';
        }

        matches.forEach(m => {
            const li = el('div', { class: 'list-item' });
            const regex = new RegExp(`(${q})`, 'i');
            li.innerHTML = `<div class="name">${m.replace(regex, '<b>$1</b>')}</div>`;
            li.addEventListener('click', () => {
                input.value = m;
                list.innerHTML = '';
                list.style.display = 'none';
                updateMinNotional();
            });
            list.appendChild(li);
        });
    });

    document.addEventListener('click', (e) => {
        if (!input.contains(e.target)) {
            list.style.display = 'none';
        }
    });
}
function renderBots(list){
  const root = document.getElementById('bots_list');
  root.innerHTML = '';
  if(!list || !list.length){ root.innerHTML = '<div class="small">No bots yet.</div>'; return; }

  list.forEach(b=>{
    const long_status_text = String(b.long_status||'No trade');
    const short_status_text = String(b.short_status||'No trade');
    const long_closed = long_status_text.startsWith('Closed');
    const short_closed = short_status_text.startsWith('Closed');
    const bothClosed = long_closed && short_closed;

    const card = document.createElement('div');
    card.className = 'bot-card';

    const head = document.createElement('div');
    head.className = 'bot-head';
    
    const left_head = document.createElement('div');
    const mark_price = b.mark_price != null ? Number(b.mark_price).toFixed(5) : '-';
    left_head.innerHTML = `
      <div class="bot-title">${b.name||'-'}</div>
      <div class="bot-meta">Coin: <b id="sym-${b.id}">${b.symbol||'-'}</b></div>
      <div class="bot-meta">Market Price: <b class="price" id="mark-${b.id}">${mark_price}</b></div>
    `;

    const right_head = document.createElement('div');
    right_head.style.textAlign = 'right';
    const __startTs = (b.started_at||b.start_time||b.start_ts||b.created_at);
    const started = (__startTs ? new Date((__startTs)*1000).toLocaleString() : (b.started_at_text||'-'));
    
    const long_sl_display = (b.long_sl_point != null ? `${b.long_sl_point}%` : 'N/A');
    const short_sl_display = (b.short_sl_point != null ? `${b.short_sl_point}%` : 'N/A');
    
    right_head.innerHTML = `
      <div class="bot-meta">Start at: <b id="start-${b.id}">${started}</b></div>
      <div class="bot-meta">Account: <b id="acc-${b.id}">${b.account_name||b.account||'-'}</b></div>
      <div class="bot-meta" id="sl-points-${b.id}">Current SL: L: ${long_sl_display}, S: ${short_sl_display}</div>
    `;

    head.appendChild(left_head);
    head.appendChild(right_head);

    const grid = document.createElement('div');
    grid.className = 'bot-grid';

    let lroi_display = Number(b.long_roi||0);
    let sroi_display = Number(b.short_roi||0);

    const lroi_class = (lroi_display >= 0 ? 'roi-pos' : 'roi-neg');
    const sroi_class = (sroi_display >= 0 ? 'roi-pos' : 'roi-neg');

    // --- LONG ROW WITH ENTRY PRICE ---
    const long_entry_price = b.long_entry_price ? Number(b.long_entry_price).toFixed(5) : 'N/A';
    const long_row = document.createElement('div');
    long_row.className = 'bot-row-flex';
    long_row.innerHTML = `
        <div>
            <b>Long</b> — Status: <span id="lstat-${b.id}" class="${long_status_text.includes('Running') ? 'status-ok' : 'status-warn'}">${long_status_text}</span>
            <span class="small" style="margin-left: 10px;">Entry: ${long_entry_price}</span>
        </div>
        <div>ROI: <span class="roi ${lroi_class}" id="lroi-${b.id}">${lroi_display.toFixed(2)}%</span></div>
    `;
    
    // --- SHORT ROW WITH ENTRY PRICE ---
    const short_entry_price = b.short_entry_price ? Number(b.short_entry_price).toFixed(5) : 'N/A';
    const short_row = document.createElement('div');
    short_row.className = 'bot-row-flex';
    short_row.innerHTML = `
        <div>
            <b>Short</b> — Status: <span id="sstat-${b.id}" class="${short_status_text.includes('Running') ? 'status-ok' : 'status-warn'}">${short_status_text}</span>
            <span class="small" style="margin-left: 10px;">Entry: ${short_entry_price}</span>
        </div>
        <div>ROI: <span class="roi ${sroi_class}" id="sroi-${b.id}">${sroi_display.toFixed(2)}%</span></div>
    `;

    grid.appendChild(long_row);
    grid.appendChild(short_row);

    const foot = document.createElement('div');
    foot.style.marginTop = '12px';
    if(!bothClosed){
      const btn = document.createElement('button');
      btn.className = 'btn btn-danger';
      btn.textContent = 'Close trade';
      btn.addEventListener('click', async ()=>{
        btn.disabled = true;
        const r = await fetch('/bots/close/'+b.id, {method:'POST'});
        try { await r.json(); } catch(e){}
        btn.disabled = false;
        await refreshBots(currentPage);
      });
      foot.appendChild(btn);
    } else {
      const btn = document.createElement('button');
      btn.className='btn btn-warning';
      btn.textContent='Closed';
      btn.disabled = true;
      foot.appendChild(btn);
    }

    card.appendChild(head);
    card.appendChild(grid);
    card.appendChild(foot);
    root.appendChild(card);
  });
}
async function refreshBots(page = currentPage){
    document.getElementById('page_info').textContent = `${page}`;
    const r=await fetch(`/bots/list?page=${page}`);
    const d=await r.json();
    renderBots(d.items||[]);
    document.getElementById('btn_next').disabled = (d.items.length < 5);
    document.getElementById('btn_prev').disabled = (page <= 1);
}
document.getElementById('r_add').addEventListener('click',()=>{R_points.push(null);renderR();});
document.getElementById('btn_save_tpl').addEventListener('click',async()=>{const body=getFormPayload();if(!body.name){alert('Bot name required');return;}await fetch('/templates/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});await loadTemplates();alert('Template saved');});
function getFormPayload(){return{name:bot_name.value.trim(),account_id:parseInt(bot_account.value||0),symbol:bot_symbol.value.trim().toUpperCase(),margin_mode:document.getElementById('margin_mode').value,long_enabled:long_on.checked?1:0,long_leverage:parseInt(long_lev.value||0),long_amount:parseFloat(long_amt.value||0),short_enabled:short_on.checked?1:0,short_leverage:parseInt(short_lev.value||0),short_amount:parseFloat(short_amt.value||0),r_points:R_points.filter(p => p !== null && !isNaN(p)),cond_sl_close:cond_sl_close.checked?1:0,cond_trailing:cond_trailing.checked?1:0,cond_close_last:cond_close_last.checked?1:0};}
document.getElementById('btn_submit').addEventListener('click',async()=>{const body=getFormPayload();if(!body.name||!body.account_id||!body.symbol){alert('Name, account and symbol required');return;}if(!body.long_enabled&&!body.short_enabled){alert('Enable Long and/or Short');return;}const r=await fetch('/bots/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await safeJson(r);if(d.error||!d.ok){alert('Submit failed: '+(d.error||d.__raw||'unknown'));return;}await refreshBots();alert('Bot submitted');});

document.getElementById('btn_next').addEventListener('click', () => {
    currentPage++;
    refreshBots(currentPage);
});
document.getElementById('btn_prev').addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        refreshBots(currentPage);
    }
});

function initSocket(){
  sio = io();
  sio.on('bot_roi', p=>{
    if(!p || !p.bot_id) return;
    const id = p.bot_id;
    const m = document.getElementById('mark-'+id);
    const sl_el = document.getElementById('sl-points-'+id);

    const longStatusEl = document.getElementById('lstat-'+id);
    const shortStatusEl = document.getElementById('sstat-'+id);
    
    const long_closed = (longStatusEl && longStatusEl.textContent.includes('Closed'));
    const short_closed = (shortStatusEl && shortStatusEl.textContent.includes('Closed'));
    
    if (!long_closed || !short_closed) {
      if(m) m.textContent = (p.mark_price!=null) ? p.mark_price.toFixed(5) : '-';
    } else {
      if(m) m.textContent = '-';
    }

    let l_sl = (p.long_sl_point != null ? `${p.long_sl_point}%` : 'N/A');
    let s_sl = (p.short_sl_point != null ? `${p.short_sl_point}%` : 'N/A');
    if (sl_el) sl_el.innerHTML = `Current SL: L: ${l_sl}, S: ${s_sl}`;

    if (!long_closed) {
        const l = document.getElementById('lroi-'+id);
        if(l){ const v=Number(p.long_roi||0); l.textContent=v.toFixed(2)+'%'; l.className='roi '+(v>=0?'roi-pos':'roi-neg'); }
    }
    
    if (!short_closed) {
        const s = document.getElementById('sroi-'+id);
        if(s){ const v=Number(p.short_roi||0); s.textContent=v.toFixed(2)+'%'; s.className='roi '+(v>=0?'roi-pos':'roi-neg'); }
    }
  });

  sio.on('bot_status_update', p=>{
    if(!p || !p.bot_id) return;
    console.log(`Received status update for bot ${p.bot_id}, refreshing list...`);
    refreshBots();
  });
}

async function loadTemplates(){const r=await fetch('/templates/list');const d=await r.json();renderTemplates(d.items||[]);}
async function hydrateDashboard(){
    R_points = [null, null, null, null, null];
    renderR();
    await initSymbolSuggest(); 
    await updateMinNotional();
    await loadTemplates();
    await refreshBots();
    initSocket();
}
window.hydrateDashboard=hydrateDashboard;

async function updateMinNotional(){
    const sym=(bot_symbol.value||'').toUpperCase();
    const longAmtEl = document.getElementById('long_amt');
    const shortAmtEl = document.getElementById('short_amt');
    
    if(!sym){
        longAmtEl.placeholder = 'Min notional $';
        shortAmtEl.placeholder = 'Min notional $';
        return;
    }
    try{
        const r=await fetch('/api/symbol-info?symbol='+encodeURIComponent(sym));
        const d=await r.json();
        if(d.min_notional!=null){
            const n = Number(d.min_notional||0);
            if (n > 0) {
                longAmtEl.placeholder = 'Min notional $' + n;
                shortAmtEl.placeholder = 'Min notional $' + n;
            } else {
                longAmtEl.placeholder = 'Min notional $';
                shortAmtEl.placeholder = 'Min notional $';
            }
        }
    } catch(e) {
        longAmtEl.placeholder = 'Min notional $';
        shortAmtEl.placeholder = 'Min notional $';
    }
}