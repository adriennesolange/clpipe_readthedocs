import logging

from .config.package import APPLICATION_NAME

# Initialize logging config - this must be present for logging messages to work
logging.basicConfig(level=logging.WARNING, 
    format='%(message)s')

# Initalize the main clpipe logger with 'INFO' level default
logger = logging.getLogger(APPLICATION_NAME)
logger.setLevel(logging.INFO)

# Clear the main logger's handlers to avoid double printing when sub loggers
# are used.
logger.handlers = []