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
            work_item = work_queue.get(block=True)
            if work_item is not None:
                work_item.run()
                del work_item  # backport from 3.4
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


class RequestWrapper():
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
        """Create a request for the form submission.
        @param response_url: base url for a relative `action` of the form
        @param session: seesion to use fot the request
        """
        action = urlparse.urljoin(response_url, self.action)
        params, data = self.fields.copy(), None
        if self.method.lower() != 'get':
            data, params = params, None
        return RequestWrapper(session, self.method, action, params=params, data=data, **kwargs)

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
    def __init__(self, max_workers, download_delay):
        assert isinstance(download_delay, (int, float))
        self._executor = ThreadPoolExecutor(max_workers)
        self.response_queue = queue.Queue()
        self._last_request_time = 0
        self.download_delay = download_delay
        self.request_count = 0
        self.total_request_time = 0.0
        self.lock = threading.Lock()

    def get_unfinished_requests_count(self):
        return self._executor._work_queue.unfinished_tasks

    def enqueue_request(self, request):
        assert isinstance(request, RequestWrapper)

        now = time.time()
        if now - self._last_request_time < self.download_delay:
            # the request was not scheduled - please come later, you are coming too fast
            return None
        self._last_request_time = now

        def do_request(_request=request):
            """Send a request in a worker thread.
            """
            start_time = time.time()
            result = _request.session.request(*_request.args, **_request.kwargs)
            with self.lock:
                self.request_count += 1
                self.total_request_time += time.time() - start_time
            return result

        future = self._executor.submit(do_request)

        def on_request_done(_future, _request=request):
            self.response_queue.put((_request, _future))

        future.add_done_callback(on_request_done)
        return future


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

            future = None
            try:
                # use previously unused object or get a new one
                if obj is None:
                    obj = next(callback_results)  # request or item
            except StopIteration:
                pass
            else:
                if isinstance(obj, RequestWrapper):
                    # try to schedule a request
                    future = self.downloader.enqueue_request(obj)
                    if future is not None:
                        # the request was successfully enqueued - do not try again
                        obj = None
                elif isinstance(obj, dict):  # it's an item
                    self.pipeline.process_item(obj)
                    obj = None
                    continue  # processing items is a priority
                else:
                    raise TypeError('Expected a Request or a dict instance')

            try:
                # if a request was successfully schedules do not wait much for an item
                # to take the next obj from callback ASAP
                timeout = 0.0 if future is not None else 0.01
                request, future = self.downloader.response_queue.get(timeout=timeout)
            except queue.Empty:
                if not obj and not self.downloader.get_unfinished_requests_count():
                    # no more scheduled requests and objects from callbacks
                    break  # the spider finished its work
            else:
                exc = future.exception()
                if exc:
                    # logger.error('There was an exception: %s\n%s',
                    #              exc, '\n'.join(traceback.format_tb(exc.__traceback__)))
                    if request.errback:
                        _callback_results = request.errback(exc, request.session, request)
                else:
                    if request.callback:
                        _callback_results = request.callback(request.session, future.result())


class Spider():
    """
    """
    start_urls = ['http://m.rasp.yandex.ru/direction?city=213']

    def start_requests(self):
        for url in self.start_urls:
            session = requests.Session()
            yield RequestWrapper(session, 'GET', url, callback=self.parse)

    def parse(self, session, response):
        html = lhtml.fromstring(response.content)
        directions = html.xpath('//div[@class="b-choose-geo"]/ul/li/a')
        for direction in directions:
            direction_url = direction.xpath('./@href')[0]
            if 'direction=_unknown' in direction_url:
                continue
            direction_url = urlparse.urljoin(response.url, direction_url)
            direction_name = direction.xpath('./text()')[0]
            # if 'горьковское' not in direction_name.lower():
            #     continue
            yield RequestWrapper(session, 'GET', direction_url, callback=self.parse_direction)
            # return

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


class Pipeline():
    """
    """
    def __init__(self):
        self.item_count = 0

    def process_item(self, item):
        self.item_count += 1
        print('Station: {direction_name}, {station_name} ({station_id})'.format(**item))


class Command(BaseCommand):

    help = ''

    def handle(self, **options):

        downloader = Downloader(5, 0.0)
        pipeline = Pipeline()
        spider_engine = SpiderEngine(
            spider=Spider(),
            pipeline=pipeline,
            downloader=downloader
        )

        start_time = time.time()

        spider_engine.start()

        total_time = time.time() - start_time
        print('Total time: {:.1f} seconds'.format(total_time))
        total_requests = downloader.request_count
        total_request_time = downloader.total_request_time
        print('Total request count: {:d}'.format(total_requests))
        print('Cumulative request time: {:.1f} seconds'.format(total_request_time))
        print('Average request time: {:.2f} seconds'.format(total_request_time / total_requests))
        print('Requests per second: {:.2f}'.format(total_requests / total_time))
        print('Items scraped: {:d}'.format(pipeline.item_count))

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
