import logging.config
import sys
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from requests import Session


logger = logging.getLogger(__name__)


class MyThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers, queue_max_size=None):
        super(MyThreadPoolExecutor, self).__init__(max_workers)
        # limit work queue size: http://bugs.python.org/issue14119
        if queue_max_size is None:
            queue_max_size = max_workers * 2 + 1
        self._work_queue = queue.Queue(queue_max_size)


class AsyncSession(Session):

    def __init__(self, max_workers=5, *args, **kwargs):
        """Create an AsyncSession

        ProcessPoolExecutor is not supported because Response objects are not picklable.
        If you provide both `executor` and `max_workers`, the latter is ignored and provided
        executor is used as is.
        """
        super(AsyncSession, self).__init__(*args, **kwargs)
        self.executor = MyThreadPoolExecutor(max_workers=max_workers)

    def request(self, *args, callback=None, errback=None, **kwargs):
        """Maintains the existing api for Session.request.

        Used by all of the higher level methods, e.g. Session.get.
        """
        def request_done(_future):
            logger.debug('Request done in thread %s', threading.current_thread())
            exc = _future.exception()
            if exc:
                if errback:
                    errback(exc)
            else:
                if callback:
                    callback(_future.result())

        logger.debug('AsyncSession.request in thread %s', threading.current_thread())
        future = self.executor.submit(
            super(AsyncSession, self).request, *args, **kwargs)  # Future object
        future.add_done_callback(request_done)

        return future


class Spider():

    start_urls = [
        'http://m.rasp.yandex.ru/direction?city=213',
    ]
    download_delay = 0.5  # seconds

    def __init__(self):
        self.session = AsyncSession(max_workers=5)

    # @property
    # def start_urls(self):
    #     for i in range(50):
    #         print('yielding url #%s' % i)
    #         yield 'http://github.com/warvariuc/'

    def start_requests(self):
        for url in self.start_urls:
            self.start_request(url)
            time.sleep(self.download_delay)

    def start_request(self, url):
        self.session.get(url, callback=self.parse, errback=self.error)

    def parse(self, response):
        print('callback %s %s' % (response.url, response.status_code))

    def error(self, exc):
        print('There was an exception: %s' % exc)


LOGGING_CFG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        __name__: {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    }
}
logging.config.dictConfig(LOGGING_CFG)


Spider().start_requests()
