import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()
