"""One checkout worker process. The storm harness SIGKILLs these at random."""
import os
import random
import sys
import uuid

from checkout import Declined, checkout_in_transaction, checkout_saga
from common import shop

MODE = sys.argv[1]                       # transaction | saga
STOP = sys.argv[2]                       # stop file
handler = checkout_in_transaction if MODE == "transaction" else checkout_saga

conn = shop()
while not os.path.exists(STOP):
    key = f"co_{uuid.uuid4().hex[:16]}"
    sku = f"SKU-{random.randint(1, 500)}"
    card = "card_declined" if random.random() < 0.05 else "card_ok"
    try:
        handler(conn, key, sku, random.randint(1500, 90000), card)
    except Declined:
        pass
