__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import logging.config
from urllib import parse as urlparse
import traceback
import itertools
import time
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, thread as futures_thread

import requests
from lxml import html as lhtml

from django.core.management.base import BaseCommand

from trains.models import Region, Direction, Station


logger = logging.getLogger(__name__)


# monkey patching: http://bugs.python.org/issue14119#msg207512
def _worker(executor_reference, work_queue):
    try:
        while True:
            # print(threading.current_thread().name, 'Trying to get a work item')
            work_item = work_queue.get(block=True)
            if work_item is not None:
                # print(threading.current_thread().name, 'Got an work item', work_item.fn)
                work_item.run()
                del work_item  # backport from 3.4
                # print(threading.current_thread().name, 'Task done')
                work_queue.task_done()  # <-- added this line
                continue
            # print(threading.current_thread().name, 'No work item for now')
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


class Request():
    """A proxy to
    """
    def __init__(self, session, method, url, *args, callback=None, errback=None, **kwargs):
        assert callback or errback, 'A callback must be specified'
        self.session = session
        self.method = method
        self.url = url
        self.args = (method, url) + args
        self.kwargs = kwargs
        self.callback = callback
        self.errback = errback


class Form():
    """
    """
    def __init__(self, response_html_doc, form_name='', form_number=0, form_xpath=''):
        form = self._find_form_(response_html_doc, form_name, form_number, form_xpath)
        self.method = form.method
        self.action = form.action
        self.fields = dict(form.form_values())

    def to_request(self, response_url, session, **kwargs):
        action = urlparse.urljoin(response_url, self.action)
        params, data = self.fields, None
        if self.method.lower() != 'get':
            data, params = params, None
        return Request(session, self.method, action, params=params, data=data, **kwargs)

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
                while el is not None:
                    if el.tag == 'form':
                        return el
                    el = el.getparent()
            raise ValueError('No <form> element found with %s' % form_xpath)

        # If we get here, it means that either formname was None or invalid
        if form_number is not None:
            try:
                form = forms[form_number]
            except IndexError:
                raise IndexError("Form number %d not found in doc" % form_number)
            else:
                return form


class Downloader():
    """
    """
    download_delay = 0.1

    def __init__(self, max_workers, queue_max_size=None):
        self._executor = ThreadPoolExecutor(max_workers)
        self.response_queue = queue.Queue()
        self._last_request_time = 0

    def enqueue_request(self, request):
        assert isinstance(request, Request)

        now = time.time()
        if now - self._last_request_time < self.download_delay:
            # the request was not scheduled - please come later
            return None
        self._last_request_time = now

        # the queue may be full, so the next call will block until the queue gets some room
        future = self._executor.submit(request.session.request, *request.args, **request.kwargs)
        logger.debug('%s send_request %s %s',
                     threading.current_thread().name, request.method, request.url)
        future.add_done_callback(lambda _future: self.response_queue.put((request, _future)))
        time.sleep(self.download_delay)
        return future


class Spider():
    """
    """
    start_urls = ['http://m.rasp.yandex.ru/direction?city=213']

    def start_requests(self):
        for url in self.start_urls:
            session = requests.Session()
            yield Request(session, 'GET', url, callback=self.parse)

    def parse(self, session, response):
        html = lhtml.fromstring(response.content)
        directions = html.xpath('//div[@class="b-choose-geo"]/ul/li/a')
        for direction in directions:
            direction_url = direction.xpath('./@href')[0]
            if 'direction=_unknown' in direction_url:
                continue
            direction_url = urlparse.urljoin(response.url, direction_url)
            direction_name = direction.xpath('./text()')[0]
            if 'горьковское' not in direction_name.lower():
                 continue
            yield Request(session, 'GET', direction_url, callback=self.parse_direction)
            return

    def parse_direction(self, session, response):
        html = lhtml.fromstring(response.content)

        direction = html.xpath('//select[@id="id_direction"]/option[@selected]')[0]
        direction_name = direction.xpath('./text()')[0]
        direction_id = direction.xpath('./@value')[0]

        route_form = Form(html, form_name='web')
        route_form.fields['mode'] = 'all'

        stations = html.xpath('//select[@id="id_station_from"]/option')
        for station_no, station in enumerate(stations):
            station_id = int(station.xpath('./@value')[0])
            if not station_id:
                continue  # separator
            station_name = station.xpath('./text()')[0]
            station_item = {
                'direction_name': direction_name,
                'direction_id': direction_id,
                'station_name': station_name,
                'station_id': station_id,
            }
            yield station_item

            if station_no > 0 and station_id:
                route_form.fields['station_to'] = station_id
                yield route_form.to_request(response.url, session, callback=self.parse_route)
                # return

    def parse_route(self, session, response):
        print('parse_route', response.url)
        pass


class SpiderEngine():
    """
    """
    def __init__(self, spider, pipeline, downloader):
        self.spider = spider
        self.pipeline = pipeline
        self.downloader = downloader

    def start(self):

        callback_results = []  # cumulative results from all callbacks
        _callback_results = self.spider.start_requests()
        obj = None

        while True:
            if _callback_results:
                callback_results = itertools.chain(iter(_callback_results), callback_results)
                _callback_results = []

            try:
                # use previously unused object or get a new one
                obj = obj or next(callback_results)  # request or item
            except StopIteration:
                pass
            else:
                if isinstance(obj, Request):
                    # try to schedule a request
                    future = self.downloader.enqueue_request(obj)
                    if future is not None:
                        # the request was successfully enqueued
                        obj = None
                elif isinstance(obj, dict):
                    # it's an item
                    self.pipeline.process_item(obj)
                    obj = None
                    continue  # prcessing items is a priority
                else:
                    raise TypeError('Expected a Request or a dict instance')

            try:
                request, future = self.downloader.response_queue.get(timeout=0.01)
            except queue.Empty:
                pass
            else:
                logger.debug('%s Request done %s %s',
                             threading.current_thread().name, request.method, request.url)
                exc = future.exception()
                if exc:
                    logger.error('There was an exception: %s\n%s',
                                 exc, '\n'.join(traceback.format_tb(exc.__traceback__)))
                    if request.errback:
                        _callback_results = request.errback(exc, request.session, request)
                else:
                    if request.callback:
                        _callback_results = request.callback(request.session, future.result())


class Pipeline():
    """
    """
    def process_item(self, item):
        print('Station: {direction_name}, {station_name} ({station_id})'.format(**item))


class Command(BaseCommand):

    help = ''

    def handle(self, **options):

        spider_engine = SpiderEngine(
            spider=Spider(),
            pipeline=Pipeline(),
            downloader=Downloader(5)
        )
        spider_engine.start()

        # Region.objects.all().delete()
        # Direction.objects.all().delete()
        # Station.objects.all().delete()
        #
        # moscow_region = Region.objects.create(id=215, name='Москва')

        # logger.debug('Waiting for stations')
        # while (spider.downloader.get_unfinished_tasks_count()
        #        or not spider.collected_stations.empty()):
        #     try:
        #         item = spider.collected_stations.get(timeout=0.25)
        #     except queue.Empty:
        #         print('unfinished_tasks_count', spider.downloader.get_unfinished_tasks_count(),
        #               threading.current_thread().name)
        #         continue
        #     # direction = Direction.objects.filter(id=item['direction_id']).first()
        #     # if direction is None:
        #     #     direction = Direction.objects.create(
        #     #         id=item['direction_id'], name=item['direction_name'], region=moscow_region)
        #     # else:
        #     #     assert direction.name == item['direction_name'], '%r != %r' % (
        #     #         direction.name, item['direction_name'])
        #     #
        #     # station = Station.objects.filter(id=item['station_id']).first()
        #     # if station is None:
        #     #     station = Station.objects.create(
        #     #         id=item['station_id'], name=item['station_name'])
        #     # else:
        #     #     assert station.name == item['station_name'], '%r != %r' % (
        #     #         station.name, item['station_name'])
        #     # station.directions.add(direction)
        #
        #     print('Station: {direction_name}, {station_name} ({station_id})'.format(**item))
