"""Single-merchant, synthetic-data hackathon demo; not a production marketplace."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
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
        CREATE TABLE IF NOT EXISTS purchases(
            id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, status TEXT NOT NULL,
            checkout_token_hash TEXT NOT NULL, paypal_order_id TEXT UNIQUE, capture_id TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id TEXT NOT NULL,
            event TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')
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

class CreatePurchase(BaseModel):
    dataset_id: str
    intent: BuyerIntent

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
    try:
        return await ai.match(intent.goal,items)
    except Exception:
        raise HTTPException(502,'AI matching unavailable; no purchase was initiated')

@app.post('/api/purchases')
async def create(req:CreatePurchase):
    item=get_entry(req.dataset_id)
    if item is None: raise HTTPException(404,'Unknown dataset')
    if not evaluate(item,req.intent)['eligible']:
        raise HTTPException(422,'The requested dataset does not meet your declared rights and budget constraints')
    if not paypal.configured():
        raise HTTPException(503,'PayPal sandbox credentials have not been configured')
    pid=str(uuid.uuid4())
    checkout_token=secrets.token_urlsafe(32)
    checkout_token_hash=hashlib.sha256(checkout_token.encode()).hexdigest()
    with connection() as db:
        db.execute('INSERT INTO purchases(id,dataset_id,status,checkout_token_hash,created_at) VALUES(?,?,?,?,?)',
                   (pid,item['id'],'CREATING',checkout_token_hash,datetime.now(timezone.utc).isoformat()))
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
    if row['status']!='ORDER_CREATED' or not row['paypal_order_id']:
        raise HTTPException(409,'This purchase has not entered checkout')
    item=get_entry(row['dataset_id'])
    response=await paypal.capture_order(pid,row['paypal_order_id'])
    capture_id=paypal.capture_verified(response,pid,item)
    if not capture_id: raise HTTPException(502,'PayPal did not confirm the exact order and amount; access not granted')
    with connection() as db:
        db.execute("UPDATE purchases SET status='COMPLETED',capture_id=? WHERE id=? AND status='ORDER_CREATED'",(capture_id,pid))
        event(db,pid,'PAYPAL_CAPTURE_VERIFIED')
    return {'purchase_id':pid,'status':'COMPLETED','access_token':token_for(pid),'capture_id':capture_id}

@app.get('/api/purchases/{pid}/receipt')
def receipt(pid:str,authorization:Annotated[str|None,Header()]=None):
    row=authorized(pid,authorization)
    item=get_entry(row['dataset_id'])
    return {'sandbox':True,'purchase_id':pid,'paypal_order_id':row['paypal_order_id'],
            'paypal_capture_id':row['capture_id'],'dataset_id':item['id'],'dataset_name':item['name'],
            'price_usd':item['price'],'sha256':item['sha256'],'license_id':item['license_id'],
            'commercial':item['commercial'],'training':item['training'],
            'redistribution':item['redistribution'],'provenance':item['provenance'],
            'notice':'Synthetic dataset and illustrative license only. Not a legal certification.'}

@app.get('/api/purchases/{pid}/download')
def download(pid:str,authorization:Annotated[str|None,Header()]=None):
    row=authorized(pid,authorization)
    item=get_entry(row['dataset_id'])
    return FileResponse(DATA/item['filename'],filename=item['filename'],media_type='text/csv')

app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='web')
