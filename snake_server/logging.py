import logging
from logging.handlers import RotatingFileHandler

def setup_loggers(console_level=logging.INFO):
    default_formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s: %(message)s')
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(default_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = RotatingFileHandler('webserver.log', maxBytes=5*1024*1024, backupCount=2)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(default_formatter)
    root_logger.addHandler(file_handler)

