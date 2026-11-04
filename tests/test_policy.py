from decimal import Decimal
from app.catalog import get_entry, entries
from app.policy import BuyerIntent, evaluate
from app.paypal import capture_verified


def buyer(**changes):
    d={'goal':'Commercial customer support classification','max_budget':Decimal('35.00'),
       'commercial':True,'training':True,'redistribution':False}
    d.update(changes)
    return BuyerIntent(**d)


def test_product_eligible():
    assert evaluate(get_entry('support-intent'),buyer())['eligible']


def test_commercial_restricted():
    r=evaluate(get_entry('civic-dialogue'),buyer())
    assert not r['eligible'] and 'Not licensed for commercial use' in r['reasons']


def test_budget_restricted():
    assert not evaluate(get_entry('retail-demand'),buyer())['eligible']


def test_redistribution_restricted():
    assert not evaluate(get_entry('support-intent'),buyer(redistribution=True))['eligible']
    assert evaluate(get_entry('safe-security'),buyer(redistribution=True))['eligible']


def test_hashes_are_64_hex():
    assert all(len(item['sha256']) == 64 for item in entries())


def test_capture_requires_exact_reference_and_amount():
    item=get_entry('support-intent')
    response={'status':'COMPLETED','purchase_units':[{'reference_id':'purchase-123',
              'payments':{'captures':[{'id':'CAPTURE-ID','status':'COMPLETED','amount':{'currency_code':'USD','value':item['price']}}]}}]}
    assert capture_verified(response,'purchase-123',item)=='CAPTURE-ID'
    assert capture_verified(response,'different',item) is None
    response['purchase_units'][0]['payments']['captures'][0]['amount']['value']='1.00'
    assert capture_verified(response,'purchase-123',item) is None
