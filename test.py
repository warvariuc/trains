import logging.config
import sys
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, thread as futures_thread
from urllib import parse as urlparse
import traceback

import requests
from lxml import etree, html as lhtml


logger = logging.getLogger(__name__)


# monkey patching: http://bugs.python.org/issue14119#msg207512
def _worker(executor_reference, work_queue):
    try:
        while True:
            work_item = work_queue.get(block=True)
            if work_item is not None:
                work_item.run()
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


class Downloader():
    """
    """
    def __init__(self, max_workers, queue_max_size=None):
        self.executor = ThreadPoolExecutor(max_workers)
        # limit work queue size: http://bugs.python.org/issue14119
        if queue_max_size is None:
            queue_max_size = max_workers * 2 + 1
        self.executor._work_queue = queue.Queue(queue_max_size)

    @property
    def unfinished_task_counts(self):
        return self.executor._work_queue.unfinished_tasks

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


class Form():
    """
    """
    def __init__(self, url, html_doc, form_name='', form_number=0, form_xpath=''):
        form = self._find_form_(html_doc, form_name, form_number, form_xpath)
        self.method = form.method
        self.action = urlparse.urljoin(url, form.action)
        self.fields = dict(form.form_values())

    # https://github.com/scrapy/scrapy/blob/master/scrapy/http/request/form.py
    def _find_form_(self, root, form_name, form_number, form_xpath):
        """Find the form element
        """
        forms = root.xpath('//form')
        if not forms:
            raise ValueError("No <form> element found in doc")

        if form_name:
            f = root.xpath('//form[@name="%s"]' % form_name)
            if f:
                return f[0]

        # Get form element from xpath, if not found, go up
        if form_xpath:
            nodes = root.xpath(form_xpath)
            if nodes:
                el = nodes[0]
                while True:
                    if el.tag == 'form':
                        return el
                    el = el.getparent()
                    if el is None:
                        break
            raise ValueError('No <form> element found with %s' % form_xpath)

        # If we get here, it means that either formname was None or invalid
        if form_number is not None:
            try:
                form = forms[form_number]
            except IndexError:
                raise IndexError("Form number %d not found in doc" % form_number)
            else:
                return form

    def submit(self, session, downloader, callback=None, errback=None):
        assert isinstance(downloader, Downloader)
        params, data = self.fields, None
        if self.method.lower() != 'get':
            data, params = params, None
        downloader.do_request(
            session, self.method, self.action, callback=callback, errback=errback, params=params,
            data=data)


# passing session, item and other objects as arguments to callbacks makes code thread-safer
class Spider():
    """
    """
    start_urls = ['http://m.rasp.yandex.ru/direction?city=213']
    download_delay = 0.5  # seconds
    max_workers = 5
    collected_stations = queue.Queue()

    def __init__(self):
        self.downloader = Downloader(self.max_workers)

    def start(self):
        def start_requests():
            for url in self.start_urls:
                self.start_request(url)
        logger.debug('Starting spider requests')
        self.downloader.executor.submit(start_requests)

    def start_request(self, url):
        session = requests.Session()
        self.downloader.do_request(session, 'GET', url, callback=self.parse)

    def parse(self, session, response):
        html = lhtml.document_fromstring(response.content)
        directions = html.xpath('//div[@class="b-choose-geo"]/ul/li/a')
        for direction in directions:
            direction_name = direction.xpath('./text()')[0]
            direction_url = direction.xpath('./@href')[0]
            if 'direction=_unknown' in direction_url:
                continue
            direction_url = urlparse.urljoin(response.url, direction_url)
            print('Found a direction: %s (%s)' % (direction_name, direction_url))
            item = {'direction_name': direction_name}
            self.downloader.do_request(
                session, 'GET', direction_url,
                callback=lambda session, response, item=item: self.parse_direction(
                    session, response, item))
            return

    def parse_direction(self, session, response, item):
        html = lhtml.document_fromstring(response.content)
        route_form = Form(response.url, html, form_name='web')
        route_form.fields['mode'] = 'all'
        stations = html.xpath('//select[@id="id_station_from"]/option')
        for station_no, station in enumerate(stations):
            station_id = int(station.xpath('./@value')[0])
            _item = item.copy()
            _item.update({
                'station_name': station.xpath('./text()')[0],
                'station_id': station_id,
            })
            self.collected_stations.put(_item)

            if station_no > 0 and station_id:
                route_form.fields['station_to'] = station_id
                route_form.submit(session, self.downloader, callback=self.parse_route)
                return

    def parse_route(self, session, response):
        import ipdb; from pprint import pprint; ipdb.set_trace()
        pass


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
while spider.downloader.unfinished_task_counts or not spider.collected_stations.empty():
    try:
        item = spider.collected_stations.get(timeout=0.25)
    except queue.Empty:
        continue
    print('Station: {direction_name}, {station_name} ({station_id})'.format(**item), id(item))
