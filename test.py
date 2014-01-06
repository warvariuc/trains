import logging.config
import sys
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, thread as futures_thread
from urllib import parse as urlparse
import traceback

from requests import Session
from lxml import etree


logger = logging.getLogger(__name__)


class MyThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers, queue_max_size=None):
        super(MyThreadPoolExecutor, self).__init__(max_workers)
        # limit work queue size: http://bugs.python.org/issue14119
        if queue_max_size is None:
            queue_max_size = max_workers * 2 + 1
        self._work_queue = queue.Queue(queue_max_size)


def _worker(executor_reference, work_queue):
    try:
        while True:
            work_item = work_queue.get(block=True)
            if work_item is not None:
                work_item.run()
                work_queue.task_done()
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


# monkey patching: http://bugs.python.org/issue14119#msg207512
futures_thread._worker = _worker


# passing session, item and other objects as arguments to callbacks makes code thread-safer
class Spider():

    start_urls = ['http://m.rasp.yandex.ru/direction?city=213']
    download_delay = 0.5  # seconds
    max_workers = 5

    def __init__(self):
        self.executor = MyThreadPoolExecutor(self.max_workers)
        self.collected_items = queue.Queue()

    def start(self):
        def start_requests():
            for url in self.start_urls:
                self.start_request(url)
        logger.debug('Starting spider requests')
        self.executor.submit(start_requests)

    def start_request(self, url):
        session = Session()
        self.do_request(session, 'GET', url, callback=self.parse)

    def do_request(self, session, method, url, *args, callback=None, errback=None, **kwargs):
        assert callback or errback, 'A callback must be specified'

        def request_done(_future):
            logger.debug('Request done in thread %s', threading.current_thread())
            exc = _future.exception()
            if exc:
                logger.error('There was an exception: %s\n%s',
                             exc, '\n'.join(traceback.format_tb(exc.__traceback__)))
                if errback:
                    errback(session, exc)
            else:
                if callback:
                    callback(session, _future.result())

        # the queue may be full, so the next call will block until the queue gets some room
        future = self.executor.submit(session.request, method, url, *args, **kwargs)
        logger.debug('do_request in thread %s: %s %s', threading.current_thread(), method, url)
        future.add_done_callback(request_done)
        # time.sleep(self.download_delay)

        return future

    def parse(self, session, response):
        print('parse: %s %s' % (response.url, response.status_code))
        html = etree.HTML(response.content)
        directions = html.xpath('//div[@class="b-choose-geo"]/ul/li/a')
        for direction in directions:
            direction_name = direction.xpath('./text()')[0]
            direction_url = direction.xpath('./@href')[0]
            if 'direction=_unknown' in direction_url:
                continue
            direction_url = urlparse.urljoin(response.url, direction_url)
            print('Found a direction: %s (%s)' % (direction_name, direction_url))
            item = {'direction_name': direction_name}
            self.do_request(
                session, 'GET', direction_url,
                callback=lambda session, response, item=item: self.parse_direction(session, response, item))

    def parse_direction(self, session, response, item):
        import ipdb; from pprint import pprint; ipdb.set_trace()
        print('parse_direction: %s %s' % (response.url, response.status_code))
        html = etree.HTML(response.content)
        stations = html.xpath('//select[@id="id_station_from"]/option')
        for station in stations:
            _item = item.copy()
            _item.update({
                'station_name': station.xpath('./text()')[0],
                'station_id': int(station.xpath('./@value')[0]),
            })
            self.collected_items.put(_item)
            # print('Found a station: %(direction_name)s, %(station_name)s (%(station_id)s)' % item)
        #     self.do_request(session, 'GET', direction_url, callback=self.parse_direction)


LOGGING_CFG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s.%(msecs).03d [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%H:%M:%S',
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


spider = Spider()
spider.start()
logger.debug('Waiting for the items')
while spider.executor._work_queue.unfinished_tasks or not spider.collected_items.empty():
    try:
        item = spider.collected_items.get(timeout=0.25)
    except queue.Empty:
        continue
    print('Station: {direction_name}, {station_name} ({station_id})'.format(**item), id(item))
