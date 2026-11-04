"""Non-AI gate: neither an LLM nor the client is allowed to override this."""
from decimal import Decimal
from pydantic import BaseModel, Field

class BuyerIntent(BaseModel):
    goal: str = Field(min_length=8,max_length=700)
    max_budget: Decimal = Field(gt=Decimal('0'),le=Decimal('10000'),max_digits=7,decimal_places=2)
    commercial: bool = True
    training: bool = True
    redistribution: bool = False


def evaluate(item, intent: BuyerIntent):
    reasons=[]
    if Decimal(item['price']) > intent.max_budget:
        reasons.append('Above the selected budget')
    if intent.commercial and not item['commercial']:
        reasons.append('Not licensed for commercial use')
    if intent.training and not item['training']:
        reasons.append('Not licensed for model training')
    if intent.redistribution and not item['redistribution']:
        reasons.append('Redistribution is not permitted')
    return {'eligible':not reasons,'reasons':reasons}
