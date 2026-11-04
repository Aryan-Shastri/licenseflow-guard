"""Synthetic products: rights metadata is illustrative, not legal advice."""
from hashlib import sha256
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'sample_data'

CATALOG = [
    {'id':'support-intent','name':'Customer Support Intent Mini','domain':'Customer support','price':'24.00','rows':48,'filename':'support_intent.csv',
     'description':'Synthetic support requests labeled by intent for classification experiments.',
     'license_id':'LF-DEMO-C1','commercial':True,'training':True,'redistribution':False,'provenance':'Authored synthetic sample data; no real customer records.'},
    {'id':'retail-demand','name':'Retail Demand Forecast Mini','domain':'Forecasting','price':'44.00','rows':48,'filename':'retail_demand.csv',
     'description':'Illustrative weekly product demand with promotion flags and sales.',
     'license_id':'LF-DEMO-C1','commercial':True,'training':True,'redistribution':False,'provenance':'Generated synthetic numerical samples; no real retailer records.'},
    {'id':'civic-dialogue','name':'Civic Dialogue Research Mini','domain':'NLP research','price':'12.00','rows':48,'filename':'civic_dialogue.csv',
     'description':'Synthetic moderated public-policy discussion snippets for education.',
     'license_id':'LF-DEMO-R1','commercial':False,'training':True,'redistribution':False,'provenance':'Original short synthetic examples with no actual participant data.'},
    {'id':'safe-security','name':'AI Security Evaluation Mini','domain':'Secure AI','price':'34.00','rows':48,'filename':'ai_security.csv',
     'description':'Synthetic benign and adversarial-instruction classification examples for model evaluations.',
     'license_id':'LF-DEMO-O1','commercial':True,'training':True,'redistribution':True,'provenance':'Original synthetic test text; not a validated safety benchmark.'},
]


def entries():
    result=[]
    for item in CATALOG:
        result.append({**item, 'sha256':sha256((DATA / item['filename']).read_bytes()).hexdigest()})
    return result


def get_entry(dataset_id):
    return next((x for x in entries() if x['id']==dataset_id),None)
