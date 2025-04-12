import logging

from dotenv import load_dotenv
load_dotenv()

from hatchet_sdk import Hatchet, ClientConfig
from loguru import logger

root_logger = logging.getLogger()
class PropagateHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        root_logger.handle(record)
logger.add(
    PropagateHandler(),
    level=logging.DEBUG,
    format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
)

hatchet = Hatchet(
    config=ClientConfig(
        logger=root_logger,
    )   
)
