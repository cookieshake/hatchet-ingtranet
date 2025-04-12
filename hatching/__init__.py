from dotenv import load_dotenv
load_dotenv()

from hatchet_sdk import Hatchet
from loguru import logger

hatchet = Hatchet(logger=logger)
