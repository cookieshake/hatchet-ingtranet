import logging

from dotenv import load_dotenv
load_dotenv()

from loguru import logger

logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()
