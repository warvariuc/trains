"""
Simple spider inspired by Scrapy.
Spiders, pipelines and everyting except downloader workers are running in the main thread.
There is no need to care about thread-safety in user code.
"""
__version__ = '0.4.0'
__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'


import sys


required_python_version = '3.3'  # tested with this version
if sys.version < required_python_version:
    raise SystemExit('Python %s or newer required (you are using: %s).'
                     % (required_python_version, sys.version))


from concurrent.futures import thread as futures_thread


# monkey patching: http://bugs.python.org/issue14119#msg207512
def _worker(executor_reference, work_queue):
    try:
        while True:
            work_item = work_queue.get(block=True)
            if work_item is not None:
                work_item.run()
                del work_item  # backport from 3.4 <-- added this line
                work_queue.task_done()  # <-- added this line
                continue
            executor = executor_reference()
            # Exit if:
            #   - The interpreter is shutting down OR
            #   - The executor that owns the worker has been collected OR
            #   - The executor that owns the worker has been shutdown.
            if futures_thread._shutdown or executor is None or executor._shutdown:
                # Notice other workers
                work_queue.put(None)
                return
            del executor
    except BaseException:
        futures_thread._base.LOGGER.critical('Exception in worker', exc_info=True)

futures_thread._worker = _worker


from .request import RequestWrapper
from .response import ResponseWrapper
from .spider import Spider
from .pipeline import ItemPipeline
from .item import Item
from .form import Form
from .fingerprint import UrlFingerprints
from .downloader import Downloader
from .engine import SpiderEngine
