__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import queue
import threading
from concurrent import futures
import time
import logging
import traceback

from .request import RequestWrapper
from .response import ResponseWrapper


logger = logging.getLogger(__name__)


class Downloader():
    """
    """
    def __init__(self, max_workers, download_delay):
        assert isinstance(download_delay, (int, float))
        self._executor = futures.ThreadPoolExecutor(max_workers)
        self.response_queue = queue.Queue()
        self._last_request_time = 0
        self.download_delay = download_delay
        self.request_count = 0
        self.failure_count = 0
        self.total_request_time = 0.0
        self.lock = threading.Lock()

    def get_unfinished_requests_count(self):
        return self._executor._work_queue.unfinished_tasks

    def do_request(self, request_wrapper):
        """Send a request and wait for the response in a worker thread.
        """
        assert isinstance(request_wrapper, RequestWrapper)
        logger.debug('Request to %s (thread %s)', request_wrapper.url,
                     threading.current_thread().name)
        start_time = time.time()
        try:
            response = request_wrapper.session.request(
                *request_wrapper.args, **request_wrapper.kwargs)
        except Exception as exc:
            logger.error('Request exception: %s\n%s',
                         exc, '\n'.join(traceback.format_tb(exc.__traceback__)))
            with self.lock:
                self.failure_count += 1
            response = exc
        else:
            request_time = time.time() - start_time
            logger.debug('Response from %s in %.3f s. (thread %s)', request_wrapper.url,
                         request_time, threading.current_thread().name)

            with self.lock:
                self.request_count += 1
                self.total_request_time += request_time

        response_wrapper = ResponseWrapper(response=response, request_wrapper=request_wrapper)
        self.response_queue.put(response_wrapper)

    def enqueue_request(self, request_wrapper):
        """
        """
        now = time.time()
        if now - self._last_request_time < self.download_delay:
            # the request was not scheduled - please come later, you are coming too fast
            return False
        self._last_request_time = now

        self._executor.submit(self.do_request, request_wrapper)
        return True
