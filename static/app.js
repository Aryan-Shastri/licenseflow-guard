const $ = id => document.getElementById(id);
let catalog=[], selected=null, currentEligibility={}, paypalEnabled=false, aiEnabled=false, checkoutSession=null;
let lastReceipt=null;
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
async function refreshEligibility(){
  try{const result=await request('/api/eligibility',{method:'POST',body:JSON.stringify(intent())});currentEligibility=result.results;
      renderCatalog();renderDetails();}catch(e){text($('checkout-message'),e.message);}
}
function renderCatalog(){
  const holder=$('catalog');holder.replaceChildren();text($('catalog-count'),`${catalog.length.toString().padStart(2,'0')} DATASETS`);
  for(const item of catalog){
    const eligibility=currentEligibility[item.id]||{eligible:false,reasons:['Not evaluated']};
    const button=el('button',`dataset-item ${selected===item.id?'selected':''} ${eligibility.eligible?'':'restricted'}`);
    button.setAttribute('type','button');button.setAttribute('aria-pressed',String(selected===item.id));
    const details=el('div');details.append(el('div','dataset-domain',item.domain),el('h3','',item.name),el('p','',item.description));
    details.append(el('span',`dataset-tag ${eligibility.eligible?'':'bad'}`,eligibility.eligible?'RIGHTS-MATCHED':'RESTRICTION'));
    button.append(details,el('strong','dataset-price',`$${item.price}`));button.addEventListener('click',()=>{selected=item.id;$('accept').checked=false;checkoutSession=null;renderCatalog();renderDetails()});
    holder.append(button);
  }
}
function renderDetails(){
  const item=catalog.find(x=>x.id===selected);
  $('paypal-area').replaceChildren();
  if(!item){text($('selected-title'),'Choose a dataset');return;}
  text($('selected-title'),item.name);text($('selected-domain'),item.domain);text($('selected-price'),`$${item.price}`);
  text($('selected-desc'),item.description);
  text($('selected-hash'),item.sha256);
  const flags=[['Commercial use',item.commercial],['Model training',item.training],['Redistribution',item.redistribution]];
  $('license-terms').replaceChildren(...flags.map(([name,enabled])=>{const row=el('div','license-row');row.append(el('span','',name),el('span',enabled?'yes':'no',enabled?'PERMITTED':'NOT PERMITTED'));return row}));
  const evalResult=currentEligibility[item.id]||{eligible:false,reasons:['Set an intended use first']};
  text($('eligibility-box'),evalResult.eligible?'Eligible under the selected demonstration rules.':`Not eligible: ${evalResult.reasons.join('; ')}`);
  $('eligibility-box').className=`eligibility ${evalResult.eligible?'allowed':'blocked'}`;
  if(!paypalEnabled){$('paypal-area').append(el('p','muted small','PayPal sandbox is not configured. Add server-side credentials to enable checkout.'));return}
  if(!evalResult.eligible){$('paypal-area').append(el('p','muted small','Checkout is blocked by the deterministic rights policy.'));return}
  if(!$('accept').checked){$('paypal-area').append(el('p','muted small','Review terms and select the authorization checkbox to enable PayPal checkout.'));return}
  if(!window.paypal){$('paypal-area').append(el('p','muted small','PayPal SDK is loading. Please check your connection.'));return}
  window.paypal.Buttons({
    style:{layout:'vertical',shape:'rect',label:'pay'},
    createOrder:async()=>{
      const current=selected;const result=await request('/api/purchases',{method:'POST',body:JSON.stringify({dataset_id:current,intent:intent()})});
      checkoutSession={...result,dataset_id:current};text($('checkout-message'),'PayPal sandbox order created. Approve in the PayPal window.');return result.order_id;
    },
    onApprove:async()=>{
      try{
        if(!checkoutSession)throw Error('Checkout session missing.');
        const result=await request(`/api/purchases/${checkoutSession.purchase_id}/capture`,{method:'POST',headers:{'X-Checkout-Token':checkoutSession.checkout_token}});
        lastReceipt={...result};const receipt=await request(`/api/purchases/${result.purchase_id}/receipt`,{headers:{Authorization:`Bearer ${result.access_token}`}});
        lastReceipt.receipt=receipt;text($('capture-id'),receipt.paypal_capture_id);text($('receipt-hash'),receipt.sha256);
        $('receipt').hidden=false;$('receipt').scrollIntoView({behavior:'smooth'});text($('checkout-message'),'PayPal sandbox capture verified. Dataset access granted.');
      }catch(e){text($('checkout-message'),`Capture not verified: ${e.message}`)}
    },
    onCancel:()=>text($('checkout-message'),'You cancelled PayPal checkout; no dataset was unlocked.'),
    onError:()=>text($('checkout-message'),'PayPal sandbox checkout encountered an error. Try again without modifying your order.')
  }).render('#paypal-area');
}
async function runMatch(){
  const button=$('match');button.disabled=true;text($('ai-status'),'Running rights checks and AI ranking…');
  try{
    await refreshEligibility();const result=await request('/api/match',{method:'POST',body:JSON.stringify(intent())});
    const box=$('ai-result');box.hidden=false;box.replaceChildren(el('strong','', 'AI MATCHING / ADVISORY ONLY'),el('p','',result.rationale));
    if(result.choices.length){const list=el('ul');for(const choice of result.choices){
      const item=catalog.find(x=>x.id===choice.dataset_id);
      if(item)list.append(el('li','',`${item.name}: ${choice.explanation} Limitation: ${choice.limitation}`));
    }box.append(list);selected=result.choices[0].dataset_id;renderCatalog();renderDetails();}
    text($('ai-status'),'AI matching complete. Deterministic rights checks remain authoritative.');
  }catch(e){text($('ai-status'),e.message)}finally{button.disabled=false}
}
async function saveBlob(name,blob){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function downloadDataset(){
 if(!lastReceipt)return;try{const r=await fetch(`/api/purchases/${lastReceipt.purchase_id}/download`,{headers:{Authorization:`Bearer ${lastReceipt.access_token}`}});
  if(!r.ok)throw Error('Dataset authorization failed');await saveBlob(`${lastReceipt.receipt.dataset_id}.csv`,await r.blob())}catch(e){alert(e.message)}
}
async function init(){
 try{const [cfg,items]=await Promise.all([request('/api/config'),request('/api/catalog')]);paypalEnabled=cfg.paypal_enabled;aiEnabled=cfg.ai_enabled;
   catalog=items.items;text($('ai-status'),aiEnabled?'Gemini AI enabled. Review explanations critically.':'Gemini not configured. Rights filtering remains available.');
   if(paypalEnabled){const sc=document.createElement('script');sc.src=`https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(cfg.paypal_client_id)}&currency=USD&intent=capture`;
     sc.addEventListener('load',()=>renderDetails());sc.addEventListener('error',()=>text($('checkout-message'),'Unable to load PayPal SDK.'));
     document.head.appendChild(sc);
   }await refreshEligibility();
 }catch(e){text($('catalog'),e.message)}
}
$('match').addEventListener('click',runMatch);$('filter').addEventListener('click',refreshEligibility);
$('accept').addEventListener('change',renderDetails);
for(const id of ['commercial','training','redistribution','budget','goal'])$(id).addEventListener('change',()=>{$('accept').checked=false;refreshEligibility()});
$('download').addEventListener('click',downloadDataset);
$('receipt-json').addEventListener('click',async()=>{if(lastReceipt)await saveBlob('licenseflow-receipt.json',new Blob([JSON.stringify(lastReceipt.receipt,null,2)],{type:'application/json'}))});
init();
