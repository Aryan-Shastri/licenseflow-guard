const $ = id => document.getElementById(id);
let catalog=[], selected=null, currentEligibility={}, paypalEnabled=false, aiEnabled=false, checkoutSession=null;
let activeQuote=null, lastReceipt=null;

function intent(){
  return {goal:$('goal').value.trim(),max_budget:Number($('budget').value),commercial:$('commercial').checked,
    training:$('training').checked,redistribution:$('redistribution').checked};
}

async function request(path,options={}){
  const r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const data=await r.json().catch(()=>({detail:'Unexpected server response'}));
  if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:`Request failed (${r.status})`);
  return data;
}

function text(node,value){node.textContent=value;}
function el(tag,cls,content){const node=document.createElement(tag);if(cls)node.className=cls;if(content!==undefined)text(node,content);return node;}

function resetQuote(){
  activeQuote=null;
  $('accept').checked=false;
  if($('quote-box'))$('quote-box').hidden=true;
  $('paypal-area').replaceChildren();
}

async function refreshEligibility(){
  try{
    const result=await request('/api/eligibility',{method:'POST',body:JSON.stringify(intent())});
    currentEligibility=result.results;
    resetQuote();
    renderCatalog();
    renderDetails();
  }catch(e){
    text($('checkout-message'),e.message);
  }
}

function renderCatalog(){
  const holder=$('catalog');holder.replaceChildren();text($('catalog-count'),`${catalog.length.toString().padStart(2,'0')} DATASETS`);
  for(const item of catalog){
    const eligibility=currentEligibility[item.id]||{eligible:false,reasons:['Not evaluated']};
    const button=el('button',`dataset-item ${selected===item.id?'selected':''} ${eligibility.eligible?'':'restricted'}`);
    button.setAttribute('type','button');button.setAttribute('aria-pressed',String(selected===item.id));
    const details=el('div');details.append(el('div','dataset-domain',item.domain),el('h3','',item.name),el('p','',item.description));
    const tagText=eligibility.eligible?'RIGHTS-MATCHED':`RESTRICTED: ${eligibility.reasons[0]}`;
    details.append(el('span',`dataset-tag ${eligibility.eligible?'':'bad'}`,tagText));
    button.append(details,el('strong','dataset-price',`$${item.price}`));
    button.addEventListener('click',()=>{
      selected=item.id;
      resetQuote();
      checkoutSession=null;
      renderCatalog();
      renderDetails();
    });
    holder.append(button);
  }
}

async function handleApprovalChange(){
  const item=catalog.find(x=>x.id===selected);
  const evalResult=currentEligibility[selected]||{eligible:false};
  if(!$('accept').checked){
    resetQuote();
    renderDetails();
    return;
  }
  if(!item||!evalResult.eligible){
    $('accept').checked=false;
    return;
  }
  text($('checkout-message'),'Requesting server-persisted approval quote…');
  try{
    const quote=await request('/api/quotes',{method:'POST',body:JSON.stringify({dataset_id:selected,intent:intent()})});
    activeQuote=quote;
    text($('checkout-message'),'');
    const quoteBox=$('quote-box');
    quoteBox.hidden=false;
    quoteBox.replaceChildren();
    quoteBox.append(
      el('strong','','✓ SERVER-BOUND APPROVAL QUOTE REGISTERED'),
      el('div','',`Bound to: ${quote.dataset_name} (${quote.dataset_id}) · $${quote.price_usd} ${quote.currency}`),
      el('div','',`Commercial: ${quote.commercial?'PERMITTED':'NOT PERMITTED'} | Training: ${quote.training?'PERMITTED':'NOT PERMITTED'} | Redistribution: ${quote.redistribution?'PERMITTED':'NOT PERMITTED'}`),
      el('span','quote-badge','SINGLE-USE · REPLAY-RESISTANT · 10 MIN VALIDITY')
    );
    renderPayPalButtons();
  }catch(e){
    $('accept').checked=false;
    text($('checkout-message'),`Approval quote failed: ${e.message}`);
  }
}

function renderPayPalButtons(){
  $('paypal-area').replaceChildren();
  if(!paypalEnabled){
    $('paypal-area').append(el('p','muted small','PayPal sandbox is not configured. Add server-side credentials to enable checkout.'));
    return;
  }
  if(!activeQuote){
    $('paypal-area').append(el('p','muted small','Review terms and check the approval box to generate a server quote.'));
    return;
  }
  if(!window.paypal){
    $('paypal-area').append(el('p','muted small','PayPal SDK is loading. Please check your connection.'));
    return;
  }
  window.paypal.Buttons({
    style:{layout:'vertical',shape:'rect',label:'pay'},
    createOrder:async()=>{
      if(!activeQuote)throw Error('Approval quote expired or missing. Please check the authorization box to generate a fresh quote.');
      const current=selected;
      text($('checkout-message'),'Creating server-bound PayPal order…');
      try{
        const result=await request('/api/purchases',{
          method:'POST',
          body:JSON.stringify({
            dataset_id:current,
            intent:intent(),
            quote_id:activeQuote.quote_id,
            approval_token:activeQuote.approval_token
          })
        });
        checkoutSession={...result,dataset_id:current};
        text($('checkout-message'),'PayPal sandbox order created. Complete payment in the popup window.');
        return result.order_id;
      }catch(e){
        resetQuote();
        renderDetails();
        text($('checkout-message'),`Order creation blocked: ${e.message}`);
        throw e;
      }
    },
    onApprove:async()=>{
      try{
        if(!checkoutSession)throw Error('Checkout session missing.');
        text($('checkout-message'),'Verifying PayPal capture and reconciling with order binding…');
        const result=await request(`/api/purchases/${checkoutSession.purchase_id}/capture`,{
          method:'POST',
          headers:{'X-Checkout-Token':checkoutSession.checkout_token}
        });
        lastReceipt={...result};
        const receipt=await request(`/api/purchases/${result.purchase_id}/receipt`,{
          headers:{Authorization:`Bearer ${result.access_token}`}
        });
        lastReceipt.receipt=receipt;
        text($('capture-id'),receipt.paypal_capture_id);
        text($('receipt-hash'),receipt.sha256);
        $('receipt').hidden=false;
        $('receipt').scrollIntoView({behavior:'smooth'});
        text($('checkout-message'),'PayPal sandbox capture verified. Dataset access granted.');
      }catch(e){
        text($('checkout-message'),`Capture verification failed: ${e.message}`);
      }
    },
    onCancel:()=>text($('checkout-message'),'You cancelled PayPal checkout; no payment was captured.'),
    onError:(err)=>text($('checkout-message'),'PayPal sandbox checkout encountered an error. Try again.')
  }).render('#paypal-area');
}

function renderDetails(){
  const item=catalog.find(x=>x.id===selected);
  if(!item){
    text($('selected-title'),'Choose a dataset');
    $('accept').disabled=true;
    $('paypal-area').replaceChildren();
    return;
  }
  text($('selected-title'),item.name);
  text($('selected-domain'),item.domain);
  text($('selected-price'),`$${item.price}`);
  text($('selected-desc'),item.description);
  text($('selected-hash'),item.sha256);
  const flags=[['Commercial use',item.commercial],['Model training',item.training],['Redistribution',item.redistribution]];
  $('license-terms').replaceChildren(...flags.map(([name,enabled])=>{
    const row=el('div','license-row');
    row.append(el('span','',name),el('span',enabled?'yes':'no',enabled?'PERMITTED':'NOT PERMITTED'));
    return row;
  }));
  const evalResult=currentEligibility[item.id]||{eligible:false,reasons:['Set an intended use first']};
  if(evalResult.eligible){
    text($('eligibility-box'),'✓ Dataset meets your declared budget and licensing criteria.');
    $('eligibility-box').className='eligibility allowed';
    $('accept').disabled=false;
  }else{
    text($('eligibility-box'),`PURCHASE BLOCKED: ${evalResult.reasons.join('; ')}`);
    $('eligibility-box').className='eligibility blocked';
    $('accept').disabled=true;
    $('accept').checked=false;
    $('paypal-area').replaceChildren(el('p','muted small','Checkout is blocked by deterministic rights and budget policy.'));
    return;
  }
  if(!activeQuote){
    $('paypal-area').replaceChildren(el('p','muted small','Review terms and check the approval box to generate a server quote.'));
  }
}

async function runMatch(){
  const button=$('match');button.disabled=true;text($('ai-status'),'Running deterministic rights checks and Gemini advisory ranking…');
  try{
    await refreshEligibility();
    const result=await request('/api/match',{method:'POST',body:JSON.stringify(intent())});
    const box=$('ai-result');
    box.hidden=false;
    box.replaceChildren(
      el('strong','', 'GEMINI AI ADVISORY RANKING (UNTRUSTED RECOMMENDATION)'),
      el('p','',result.rationale)
    );
    if(result.choices.length){
      const list=el('ul');
      for(const choice of result.choices){
        const item=catalog.find(x=>x.id===choice.dataset_id);
        if(item)list.append(el('li','',`${item.name}: ${choice.explanation} (Limitation: ${choice.limitation})`));
      }
      box.append(list);
      selected=result.choices[0].dataset_id;
      renderCatalog();
      renderDetails();
    }
    text($('ai-status'),'Gemini advisory complete. Deterministic policy checks remain authoritative.');
  }catch(e){
    text($('ai-status'),e.message);
  }finally{
    button.disabled=false;
  }
}

async function saveBlob(name,blob){
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=name;
  document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

async function downloadDataset(){
  if(!lastReceipt)return;
  try{
    const r=await fetch(`/api/purchases/${lastReceipt.purchase_id}/download`,{
      headers:{Authorization:`Bearer ${lastReceipt.access_token}`}
    });
    if(!r.ok)throw Error('Dataset download authorization failed');
    await saveBlob(`${lastReceipt.receipt.dataset_id}.csv`,await r.blob());
  }catch(e){alert(e.message);}
}

async function init(){
  try{
    const [cfg,items]=await Promise.all([request('/api/config'),request('/api/catalog')]);
    paypalEnabled=cfg.paypal_enabled;aiEnabled=cfg.ai_enabled;
    catalog=items.items;
    text($('ai-status'),aiEnabled?'Gemini AI enabled (advisory). Review explanations critically.':'Gemini not configured. Deterministic filtering remains active.');
    if(paypalEnabled){
      const sc=document.createElement('script');
      sc.src=`https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(cfg.paypal_client_id)}&currency=USD&intent=capture`;
      sc.addEventListener('load',()=>renderDetails());
      sc.addEventListener('error',()=>text($('checkout-message'),'Unable to load PayPal SDK.'));
      document.head.appendChild(sc);
    }
    await refreshEligibility();
  }catch(e){
    text($('catalog'),e.message);
  }
}

$('match').addEventListener('click',runMatch);
$('filter').addEventListener('click',refreshEligibility);
$('accept').addEventListener('change',handleApprovalChange);
for(const id of ['commercial','training','redistribution','budget','goal']){
  $(id).addEventListener('change',()=>{resetQuote();refreshEligibility();});
}
$('download').addEventListener('click',downloadDataset);
$('receipt-json').addEventListener('click',async()=>{
  if(lastReceipt)await saveBlob('licenseflow-receipt.json',new Blob([JSON.stringify(lastReceipt.receipt,null,2)],{type:'application/json'}));
});

init();


// --- AG STUDIO PROCUREMENT SECURITY INTELLIGENCE DASHBOARD ---
let gridApi = null;
let chartPolicyInstance = null;
let chartSpendInstance = null;
let auditTelemetryData = null;

function setupNavigation() {
  const tabMarketplace = $('tab-marketplace');
  const tabAnalytics = $('tab-analytics');
  const viewMarketplace = $('view-marketplace');
  const viewAnalytics = $('view-analytics');

  if (!tabMarketplace || !tabAnalytics) return;

  tabMarketplace.addEventListener('click', () => {
    tabMarketplace.classList.add('active');
    tabMarketplace.setAttribute('aria-selected', 'true');
    tabAnalytics.classList.remove('active');
    tabAnalytics.setAttribute('aria-selected', 'false');
    viewMarketplace.hidden = false;
    viewAnalytics.hidden = true;
  });

  tabAnalytics.addEventListener('click', () => {
    tabAnalytics.classList.add('active');
    tabAnalytics.setAttribute('aria-selected', 'true');
    tabMarketplace.classList.remove('active');
    tabMarketplace.setAttribute('aria-selected', 'false');
    viewMarketplace.hidden = true;
    viewAnalytics.hidden = false;
    loadAuditTelemetry();
  });
}

async function loadAuditTelemetry() {
  try {
    const data = await request('/api/audit/intelligence');
    auditTelemetryData = data;
    renderAuditMetrics(data.metrics);
    renderAuditGrid(data.records);
    renderAuditCharts(data.policy_breakdown, data.spend_by_dataset);
  } catch (err) {
    console.error('Failed to load audit telemetry:', err);
  }
}

function renderAuditMetrics(metrics) {
  if (!metrics) return;
  text($('metric-spend'), `$${metrics.total_spend_usd} USD`);
  text($('metric-purchases'), String(metrics.completed_purchases));
  text($('metric-refusals'), String(metrics.policy_refusals));
  text($('metric-approvals'), String(metrics.approvals_issued));
  text($('metric-security'), `${metrics.security_defenses}/${metrics.security_defenses}`);
  text($('grid-row-count'), `${auditTelemetryData ? auditTelemetryData.records.length : 0} RECORDS`);
}

function renderAuditGrid(records) {
  const gridDiv = $('procurementGrid');
  if (!gridDiv || typeof agGrid === 'undefined') return;

  if (gridApi) {
    gridApi.setGridOption('rowData', records);
    return;
  }

  const columnDefs = [
    {
      field: 'timestamp',
      headerName: 'TIMESTAMP (UTC)',
      width: 175,
      sortable: true,
      filter: true,
      valueFormatter: p => p.value ? p.value.replace('T', ' ').substring(0, 19) : ''
    },
    {
      field: 'category',
      headerName: 'CATEGORY',
      width: 140,
      sortable: true,
      filter: true
    },
    {
      field: 'dataset_name',
      headerName: 'DATASET',
      width: 220,
      sortable: true,
      filter: true
    },
    {
      field: 'amount_usd',
      headerName: 'AMOUNT',
      width: 110,
      sortable: true,
      valueFormatter: p => `$${p.value} USD`
    },
    {
      field: 'status',
      headerName: 'STATUS',
      width: 150,
      sortable: true,
      filter: true,
      cellRenderer: p => {
        const val = p.value || '';
        let cls = 'completed';
        if (val.includes('REFUSED') || val.includes('REJECTED') || val.includes('FAILED')) cls = 'refused';
        else if (val.includes('APPROVED')) cls = 'approved';
        else if (val.includes('REPLAY') || val.includes('TAMPER')) cls = 'security';
        return `<span class="grid-badge ${cls}">${val}</span>`;
      }
    },
    {
      field: 'reference_id',
      headerName: 'REFERENCE / CAPTURE',
      width: 190,
      valueFormatter: p => p.value || 'N/A'
    },
    {
      field: 'sha256',
      headerName: 'INTEGRITY SHA-256',
      width: 160,
      valueFormatter: p => p.value ? p.value.substring(0, 12) + '...' : '—'
    },
    {
      headerName: 'INSPECT',
      width: 95,
      sortable: false,
      filter: false,
      cellRenderer: p => {
        const btn = document.createElement('button');
        btn.className = 'btn-inspect';
        btn.textContent = 'DETAILS';
        btn.onclick = () => openDecisionModal(p.data);
        return btn;
      }
    }
  ];

  const gridOptions = {
    columnDefs: columnDefs,
    rowData: records,
    pagination: true,
    paginationPageSize: 10,
    domLayout: 'normal',
    rowSelection: 'single',
    animateRows: true
  };

  gridApi = agGrid.createGrid(gridDiv, gridOptions);
}

function renderAuditCharts(breakdown, spend) {
  if (typeof agCharts === 'undefined') return;

  const breakdownDiv = $('chart-policy-breakdown');
  if (breakdownDiv && !chartPolicyInstance) {
    breakdownDiv.replaceChildren();
    const breakdownOptions = {
      container: breakdownDiv,
      theme: 'ag-default-dark',
      data: breakdown,
      series: [{
        type: 'donut',
        angleKey: 'count',
        legendItemKey: 'verdict',
        fills: ['#00ff9d', '#f87171', '#38bdf8', '#fbbf24'],
        strokes: ['#080c14'],
        innerRadiusRatio: 0.58
      }]
    };
    chartPolicyInstance = agCharts.AgCharts.create(breakdownOptions);
  }

  const spendDiv = $('chart-spend-dataset');
  if (spendDiv && !chartSpendInstance) {
    spendDiv.replaceChildren();
    const spendOptions = {
      container: spendDiv,
      theme: 'ag-default-dark',
      data: spend,
      series: [{
        type: 'bar',
        xKey: 'dataset',
        yKey: 'spend',
        fill: '#00ff9d',
        stroke: '#00ff9d'
      }],
      axes: [
        { type: 'category', position: 'bottom' },
        { type: 'number', position: 'left', label: { formatter: p => `$${p.value}` } }
      ]
    };
    chartSpendInstance = agCharts.AgCharts.create(spendOptions);
  }
}

function openDecisionModal(record) {
  if (!record) return;
  const modal = $('decision-modal');
  const content = $('modal-content');
  if (!modal || !content) return;

  content.replaceChildren();

  const addRow = (label, val, isCode = false) => {
    const item = el('div', 'detail-item');
    item.append(el('span', 'detail-label', label));
    if (isCode) {
      const c = el('code', 'detail-code', String(val || '—'));
      item.append(c);
    } else {
      item.append(el('span', 'detail-value', String(val || '—')));
    }
    content.append(item);
  };

  addRow('AUDIT RECORD ID', record.id);
  addRow('TIMESTAMP (UTC)', record.timestamp);
  addRow('EVENT CATEGORY', record.category);
  addRow('EVENT TYPE', record.event_type);
  addRow('DATASET NAME', record.dataset_name);
  addRow('DATASET IDENTIFIER', record.dataset_id);
  addRow('TRANSACTION AMOUNT', `$${record.amount_usd} ${record.currency || 'USD'}`);
  addRow('STATUS & VERDICT', `${record.status} (${record.policy_verdict || 'N/A'})`);
  addRow('EXPLANATION & REASON', record.reason);
  addRow('PAYPAL REFERENCE / CAPTURE ID', record.reference_id, true);
  addRow('DATASET CONTENT HASH (SHA-256)', record.sha256, true);
  if (record.approval_id) addRow('SERVER APPROVAL QUOTE ID', record.approval_id, true);
  if (record.buyer_intent) addRow('BOUND BUYER INTENT SNAPSHOT', JSON.stringify(record.buyer_intent, null, 2), true);

  modal.hidden = false;
}

function setupAuditControls() {
  const filterSelect = $('filter-status');
  const quickSearch = $('grid-quick-search');
  const refreshBtn = $('btn-refresh-telemetry');
  const exportBtn = $('btn-export-csv');
  const modalClose = $('modal-close');
  const modal = $('decision-modal');

  if (filterSelect) {
    filterSelect.addEventListener('change', () => {
      const val = filterSelect.value.trim();
      if (!gridApi) return;
      if (val) {
        gridApi.setGridOption('quickFilterText', val);
      } else {
        gridApi.setGridOption('quickFilterText', quickSearch ? quickSearch.value : '');
      }
    });
  }

  if (quickSearch) {
    quickSearch.addEventListener('input', () => {
      if (gridApi) gridApi.setGridOption('quickFilterText', quickSearch.value);
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => loadAuditTelemetry());
  }

  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (gridApi) gridApi.exportDataAsCsv();
    });
  }

  if (modalClose) {
    modalClose.addEventListener('click', () => { if (modal) modal.hidden = true; });
  }

  if (modal) {
    modal.addEventListener('click', e => {
      if (e.target === modal) modal.hidden = true;
    });
  }

  const agentBtn = $('agent-query-btn');
  const agentInput = $('agent-query-input');
  const promptChips = document.querySelectorAll('.prompt-chip');

  const executeAgentQuery = async (queryText) => {
    if (!queryText.trim()) return;
    const box = $('agent-response-box');
    const textEl = $('agent-response-text');
    const roleEl = $('agent-role-badge');
    const catEl = $('agent-cat-badge');

    if (box) box.hidden = false;
    if (textEl) textEl.textContent = 'Querying Security Telemetry Advisor…';

    try {
      const res = await request('/api/audit/agent/query', {
        method: 'POST',
        body: JSON.stringify({ query: queryText })
      });
      if (roleEl) roleEl.textContent = res.agent_role || 'TELEMETRY ADVISOR';
      if (catEl) catEl.textContent = res.category || 'AUDIT';
      if (textEl) textEl.textContent = res.answer || 'No response';
    } catch (err) {
      if (textEl) textEl.textContent = `Agent error: ${err.message}`;
    }
  };

  if (agentBtn && agentInput) {
    agentBtn.addEventListener('click', () => executeAgentQuery(agentInput.value));
    agentInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') executeAgentQuery(agentInput.value);
    });
  }

  promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-query');
      if (agentInput) agentInput.value = q;
      executeAgentQuery(q);
    });
  });
}

setupNavigation();
setupAuditControls();
