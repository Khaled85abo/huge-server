import logging
import sys
import os
# from logtail import LogtailHandler


# get logger
logger = logging.getLogger()

# create formatter
formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s")


stream_handler = logging.StreamHandler(sys.stdout)
file_handler = logging.FileHandler("./app/logging/app.log")
# better_stack_handler = LogtailHandler(source_token= os.getenv("BETTER_STACK_LOG_TOKEN"))

# set formatter
stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)


# logger.handlers = [stream_handler,file_handler, better_stack_handler]
logger.handlers = [stream_handler,file_handler]

# set log-level
logger.setLevel(logging.INFO)