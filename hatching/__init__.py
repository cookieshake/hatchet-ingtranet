from dotenv import load_dotenv
load_dotenv()

from hatchet_sdk import Hatchet, ClientConfig
from loguru import logger

hatchet = Hatchet(
    config=ClientConfig(
        logger=logger,
    )   
)
