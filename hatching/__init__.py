import logging

from dotenv import load_dotenv
load_dotenv()

from hatchet_sdk import Hatchet, ClientConfig
from loguru import logger

logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()

class PropagateHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)

logger.add(
    PropagateHandler(),
    format="{message}",
)

hatchet = Hatchet(
    config=ClientConfig(
        logger=root_logger,
    )   
)
