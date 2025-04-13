# -*- coding:utf-8 -*-
import logging
import os
from pathlib import Path

current_dir = Path(__file__).resolve().parent
# log_dir = current_dir.parents[1]
log_dir = current_dir
log_file_path = log_dir / 'log.txt'

logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class Logger:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def info(self, msg):
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)

    def debug(self, msg):
        self.logger.debug(msg)


logger = Logger()

if __name__ == '__main__':
    logger.info('test')