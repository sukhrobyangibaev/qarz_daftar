import logging
import sys

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
