__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import queue
import threading
from concurrent import futures
import time
import logging

from .request import RequestWrapper


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
        self.total_request_time = 0.0
        self.lock = threading.Lock()

    def get_unfinished_requests_count(self):
        return self._executor._work_queue.unfinished_tasks

    def enqueue_request(self, request_wrapper):
        assert isinstance(request_wrapper, RequestWrapper)

        now = time.time()
        if now - self._last_request_time < self.download_delay:
            # the request was not scheduled - please come later, you are coming too fast
            return None
        self._last_request_time = now

        def do_request(_request_wrapper=request_wrapper):
            """Send a request in a worker thread.
            """
            logger.debug('Request to %s (thread %s)', _request_wrapper.url,
                         threading.current_thread().name)
            start_time = time.time()
            result = _request_wrapper.session.request(*_request_wrapper.args,
                                                      **_request_wrapper.kwargs)
            request_time = time.time() - start_time
            logger.debug('Response from %s in %.3f s. (thread %s)', _request_wrapper.url,
                         request_time, threading.current_thread().name)
            with self.lock:
                self.request_count += 1
                self.total_request_time += request_time
            return result

        future = self._executor.submit(do_request)

        def on_request_done(_future, _request_wrapper=request_wrapper):
            self.response_queue.put((_request_wrapper, _future))

        future.add_done_callback(on_request_done)
        return future
