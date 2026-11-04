"""Single-merchant, synthetic-data hackathon demo; not a production marketplace."""
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from .catalog import entries, get_entry, DATA
from .policy import BuyerIntent, evaluate
from . import ai,paypal

logger = logging.getLogger('licenseflow.app')

ROOT=Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env')
DB=Path(os.getenv('DATABASE_PATH',str(ROOT/'data'/'licenseflow.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
SIGNING_KEY=os.getenv('APP_SIGNING_KEY','').encode() or secrets.token_bytes(32)
app=FastAPI(title='LicenseFlow AI',version='0.1.0',docs_url='/api/docs',redoc_url=None)

def connection():
    con=sqlite3.connect(DB,timeout=5)
    con.row_factory=sqlite3.Row
    return con

def setup():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS approvals(
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            price_usd TEXT NOT NULL,
            currency TEXT NOT NULL,
            dataset_sha256 TEXT NOT NULL,
            license_id TEXT NOT NULL,
            intent_json TEXT NOT NULL,
            approval_token_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchases(
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            status TEXT NOT NULL,
            checkout_token_hash TEXT NOT NULL,
            paypal_order_id TEXT UNIQUE,
            capture_id TEXT,
            snapshot_price TEXT NOT NULL DEFAULT '',
            snapshot_currency TEXT NOT NULL DEFAULT 'USD',
            snapshot_license_id TEXT NOT NULL DEFAULT '',
            snapshot_sha256 TEXT NOT NULL DEFAULT '',
            approval_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id TEXT NOT NULL,
            event TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        ''')
        # Migrate existing DB columns if needed
        cols = {row['name'] for row in db.execute("PRAGMA table_info(purchases)").fetchall()}
        for col, col_def in [
            ('snapshot_price', "TEXT NOT NULL DEFAULT ''"),
            ('snapshot_currency', "TEXT NOT NULL DEFAULT 'USD'"),
            ('snapshot_license_id', "TEXT NOT NULL DEFAULT ''"),
            ('snapshot_sha256', "TEXT NOT NULL DEFAULT ''"),
            ('approval_id', "TEXT"),
        ]:
            if col not in cols:
                db.execute(f"ALTER TABLE purchases ADD COLUMN {col} {col_def}")
setup()

def event(db,pid,name):
    db.execute('INSERT INTO events(purchase_id,event,created_at) VALUES(?,?,?)',(pid,name,datetime.now(timezone.utc).isoformat()))

def token_for(pid):
    return hmac.new(SIGNING_KEY,pid.encode(),hashlib.sha256).hexdigest()

def purchase(pid):
    with connection() as db:
        row=db.execute('SELECT * FROM purchases WHERE id=?',(pid,)).fetchone()
    if row is None: raise HTTPException(404,'Purchase not found')
    return dict(row)

def authorized(pid, authorization):
    expected='Bearer '+token_for(pid)
    if not authorization or not hmac.compare_digest(expected, authorization):
        raise HTTPException(403,'Valid receipt token required')
    row=purchase(pid)
    if row['status']!='COMPLETED': raise HTTPException(403,'A completed sandbox payment is required')
    return row

class CreateQuote(BaseModel):
    dataset_id: str
    intent: BuyerIntent

class CreatePurchase(BaseModel):
    dataset_id: str
    intent: BuyerIntent
    quote_id: str
    approval_token: str

@app.get('/api/health')
def health():
    return {'status':'ok','sandbox_only':True}

@app.get('/api/config')
def config():
    return {'sandbox_only':True,'paypal_enabled':paypal.configured(),
            'paypal_client_id':os.getenv('PAYPAL_CLIENT_ID','') if paypal.configured() else '',
            'ai_enabled':bool(os.getenv('GEMINI_API_KEY'))}

@app.get('/api/catalog')
def catalog():
    return {'items':entries(),'sample_data_only':True}

@app.post('/api/eligibility')
def eligibility(intent:BuyerIntent):
    return {'results':{item['id']:evaluate(item,intent) for item in entries()}}

@app.post('/api/match')
async def matches(intent:BuyerIntent):
    if not os.getenv('GEMINI_API_KEY'):
        raise HTTPException(503,'Gemini API key is missing. License filters remain available; AI matching is disabled.')
    items=[item for item in entries() if evaluate(item,intent)['eligible']]
    if not items:
        return {'rationale':'No dataset passed the explicit license and budget requirements.','choices':[],'model_used':False}
    try:
        return await ai.match(intent.goal,items)
    except Exception as e:
        err_type = type(e).__name__
        logger.error("AI matching failed safely: type=%s", err_type)
        raise HTTPException(502, f'AI matching temporarily unavailable ({err_type}); deterministic license filters remain authoritative.')

@app.post('/api/quotes')
def create_quote(req:CreateQuote):
    item=get_entry(req.dataset_id)
    if item is None:
        raise HTTPException(404,'Unknown dataset')
    eval_result=evaluate(item,req.intent)
    if not eval_result['eligible']:
        raise HTTPException(422,f"Dataset ineligible: {'; '.join(eval_result['reasons'])}")
    
    quote_id=str(uuid.uuid4())
    approval_token=secrets.token_urlsafe(32)
    approval_hash=hashlib.sha256(approval_token.encode()).hexdigest()
    now=datetime.now(timezone.utc)
    expires_at=now+timedelta(minutes=10)
    
    with connection() as db:
        db.execute('''
            INSERT INTO approvals(id,dataset_id,price_usd,currency,dataset_sha256,license_id,
                                  intent_json,approval_token_hash,status,created_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?,'APPROVED',?,?)
        ''',(quote_id,item['id'],item['price'],'USD',item['sha256'],item['license_id'],
             req.intent.model_dump_json(),approval_hash,now.isoformat(),expires_at.isoformat()))
    
    return {
        'quote_id':quote_id,
        'approval_token':approval_token,
        'dataset_id':item['id'],
        'dataset_name':item['name'],
        'price_usd':item['price'],
        'currency':'USD',
        'license_id':item['license_id'],
        'commercial':item['commercial'],
        'training':item['training'],
        'redistribution':item['redistribution'],
        'sha256':item['sha256'],
        'expires_at':expires_at.isoformat(),
        'notice':'Single-use, 10-minute server-bound approval quote. Review terms carefully before checkout.'
    }

@app.post('/api/purchases')
async def create(req:CreatePurchase):
    item=get_entry(req.dataset_id)
    if item is None: raise HTTPException(404,'Unknown dataset')
    if not evaluate(item,req.intent)['eligible']:
        raise HTTPException(422,'The requested dataset does not meet your declared rights and budget constraints')
    if not paypal.configured():
        raise HTTPException(503,'PayPal sandbox credentials have not been configured')

    # Verify server-side quote and approval
    with connection() as db:
        appr=db.execute('SELECT * FROM approvals WHERE id=?',(req.quote_id,)).fetchone()
    if appr is None:
        raise HTTPException(403,'Valid approval quote required before purchase')
    
    # Expiry verification
    expires_at=datetime.fromisoformat(appr['expires_at'])
    if datetime.now(timezone.utc)>expires_at:
        raise HTTPException(410,'Approval quote has expired; request a new quote')

    # Status check (single-use, non-repayable)
    if appr['status']=='CONSUMED':
        raise HTTPException(409,'Approval quote has already been used (replay rejected)')
    if appr['status']!='APPROVED':
        raise HTTPException(403,'Approval quote is not active')

    # Validate approval token
    candidate_hash=hashlib.sha256(req.approval_token.encode()).hexdigest()
    if not hmac.compare_digest(candidate_hash,appr['approval_token_hash']):
        raise HTTPException(403,'Invalid approval token')

    # Validate integrity of bound parameters
    if appr['dataset_id']!=req.dataset_id or appr['price_usd']!=item['price'] or appr['currency']!='USD':
        raise HTTPException(422,'Approval binding parameters do not match requested purchase')

    # Atomically mark approval as CONSUMED to prevent race condition replays
    with connection() as db:
        cur=db.execute("UPDATE approvals SET status='CONSUMED' WHERE id=? AND status='APPROVED'",(req.quote_id,))
        if cur.rowcount==0:
            raise HTTPException(409,'Approval quote was already consumed by another request')

    pid=str(uuid.uuid4())
    checkout_token=secrets.token_urlsafe(32)
    checkout_token_hash=hashlib.sha256(checkout_token.encode()).hexdigest()
    now_iso=datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('''
            INSERT INTO purchases(id,dataset_id,status,checkout_token_hash,snapshot_price,
                                 snapshot_currency,snapshot_license_id,snapshot_sha256,approval_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        ''',(pid,item['id'],'CREATING',checkout_token_hash,item['price'],'USD',item['license_id'],item['sha256'],req.quote_id,now_iso))
        event(db,pid,'PURCHASE_CREATED')
    try:
        order_id=await paypal.create_order(pid,item)
    except HTTPException:
        with connection() as db:
            db.execute("UPDATE purchases SET status='FAILED' WHERE id=?",(pid,))
            event(db,pid,'ORDER_FAILED')
        raise
    with connection() as db:
        db.execute("UPDATE purchases SET status='ORDER_CREATED', paypal_order_id=? WHERE id=?",(order_id,pid))
        event(db,pid,'PAYPAL_SANDBOX_ORDER_CREATED')
    return {'purchase_id':pid,'order_id':order_id,'checkout_token':checkout_token}

@app.post('/api/purchases/{pid}/capture')
async def capture(pid:str, x_checkout_token:Annotated[str|None,Header(alias='X-Checkout-Token')]=None):
    row=purchase(pid)
    candidate=hashlib.sha256((x_checkout_token or '').encode()).hexdigest()
    if not hmac.compare_digest(candidate,row['checkout_token_hash']):
        raise HTTPException(403,'Valid checkout session token required')
    if row['status']=='COMPLETED':
        return {'purchase_id':pid,'status':'COMPLETED','access_token':token_for(pid),'capture_id':row['capture_id']}
    
    # Atomic state transition to prevent concurrent capture races
    with connection() as db:
        cursor=db.execute("UPDATE purchases SET status='CAPTURING' WHERE id=? AND status='ORDER_CREATED'",(pid,))
        if cursor.rowcount==0:
            curr=db.execute("SELECT status, capture_id FROM purchases WHERE id=?",(pid,)).fetchone()
            if curr and curr['status']=='COMPLETED':
                return {'purchase_id':pid,'status':'COMPLETED','access_token':token_for(pid),'capture_id':curr['capture_id']}
            if curr and curr['status']=='CAPTURING':
                raise HTTPException(409,'Capture already in progress')
            raise HTTPException(409,f'Cannot capture purchase in status: {curr["status"] if curr else "unknown"}')
        event(db,pid,'PAYPAL_CAPTURE_INITIATED')

    item=get_entry(row['dataset_id'])
    target_price=row['snapshot_price'] if row['snapshot_price'] else (item['price'] if item else '0.00')

    try:
        response=await paypal.capture_order(pid,row['paypal_order_id'])
    except HTTPException:
        with connection() as db:
            db.execute("UPDATE purchases SET status='FAILED' WHERE id=? AND status='CAPTURING'",(pid,))
            event(db,pid,'PAYPAL_CAPTURE_FAILED')
        raise

    capture_id=paypal.capture_verified(response,pid,{'price':target_price})
    if not capture_id:
        with connection() as db:
            db.execute("UPDATE purchases SET status='FAILED' WHERE id=? AND status='CAPTURING'",(pid,))
            event(db,pid,'PAYPAL_CAPTURE_MISMATCH')
        raise HTTPException(502,'PayPal did not confirm the exact order and amount; access not granted')

    with connection() as db:
        db.execute("UPDATE purchases SET status='COMPLETED',capture_id=? WHERE id=? AND status='CAPTURING'",(capture_id,pid))
        event(db,pid,'PAYPAL_CAPTURE_VERIFIED')
    return {'purchase_id':pid,'status':'COMPLETED','access_token':token_for(pid),'capture_id':capture_id}

@app.get('/api/purchases/{pid}/receipt')
def receipt(pid:str,authorization:Annotated[str|None,Header()]=None):
    row=authorized(pid,authorization)
    item=get_entry(row['dataset_id'])
    return {'sandbox':True,'purchase_id':pid,'paypal_order_id':row['paypal_order_id'],
            'paypal_capture_id':row['capture_id'],'dataset_id':row['dataset_id'],
            'dataset_name':item['name'] if item else row['dataset_id'],
            'price_usd':row['snapshot_price'] or (item['price'] if item else '0.00'),
            'currency':row['snapshot_currency'] or 'USD',
            'sha256':row['snapshot_sha256'] or (item['sha256'] if item else ''),
            'license_id':row['snapshot_license_id'] or (item['license_id'] if item else ''),
            'commercial':item['commercial'] if item else True,
            'training':item['training'] if item else True,
            'redistribution':item['redistribution'] if item else False,
            'provenance':item['provenance'] if item else 'Synthetic sample dataset',
            'approval_id':row['approval_id'],
            'notice':'Synthetic dataset and illustrative license only. Not a legal certification.'}

@app.get('/api/purchases/{pid}/download')
def download(pid:str,authorization:Annotated[str|None,Header()]=None):
    row=authorized(pid,authorization)
    item=get_entry(row['dataset_id'])
    if not item:
        raise HTTPException(404, 'Dataset file not found')
    file_path = DATA/item['filename']
    if not file_path.exists():
        raise HTTPException(404, 'Dataset content file missing')
    return FileResponse(file_path,filename=item['filename'],media_type='text/csv')

app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='web')
