import logging
import sys

import pymongo

# Logging
logging.basicConfig(
    format="[%(funcName)s] %(message)s",
    level=logging.INFO,
    handlers=[
        # logging.FileHandler('qarz_daftar.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# mongo db
myclient = pymongo.MongoClient('mongodb://localhost:27017/')
qarz_daftar_db = myclient['qarz_daftar']
debtors_col = qarz_daftar_db['debtors']
shops_col = qarz_daftar_db['shops']
