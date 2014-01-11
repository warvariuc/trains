"""
Simple spider inspider by Scrapy.
Spiders, pipelines and everyting except downloader workers are running in the main thread.
There is no need to care about thread-safety in user code.
Tested on Python 3.3
"""
__version__ = '0.3.0'
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
from django.db import connection

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
    """Wrapper around requests.Request
    """
    def __init__(self, session, method, url, *args, callback=None, errback=None, meta=None,
                 **kwargs):
        assert callback or errback, 'A callback must be specified'
        self.session = session
        self.method = method
        self.url = url
        self.args = (method, url) + args
        self.kwargs = kwargs
        self.callback = callback
        self.errback = errback
        self.meta = (meta or {}).copy()


class ResponseWrapper():
    """Wrapper around requests.Response
    """
    def __init__(self, response, request_wrapper):
        assert isinstance(response, requests.Response)
        assert isinstance(request_wrapper, RequestWrapper)
        self.response = response
        self.request_wrapper = request_wrapper
        self.session = request_wrapper.session
        self.meta = request_wrapper.meta.copy()

    @property
    def html_doc(self):
        """Get lxml node of the response body and cache it.
        """
        html_doc = lhtml.fromstring(self.response.content)
        self.__dict__['html_doc'] = html_doc  # memoize
        return html_doc


class Form():
    """
    """
    def __init__(self, response_wrapper, form_name='', form_number=0, form_xpath=''):
        assert isinstance(response_wrapper, ResponseWrapper)
        self.response_wrapper = response_wrapper
        form = self._find_form_(response_wrapper.html_doc, form_name, form_number, form_xpath)
        self.method = form.method
        self.action = form.action
        self.fields = dict(form.form_values())

    def to_request(self, **kwargs):
        """Create a request for the form submission.
        @param response_url: base url for a relative `action` of the form
        @param session: seesion to use fot the request
        """
        action = urlparse.urljoin(self.response_wrapper.response.url, self.action)
        params, data = self.fields.copy(), None
        if self.method.lower() != 'get':
            data, params = params, None
        return RequestWrapper(self.response_wrapper.session, self.method, action, params=params,
                              data=data, **kwargs)

    # mostly copied from https://github.com/scrapy/scrapy/blob/master/scrapy/http/request/form.py
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
            start_time = time.time()
            result = _request_wrapper.session.request(*_request_wrapper.args,
                                                      **_request_wrapper.kwargs)
            with self.lock:
                self.request_count += 1
                self.total_request_time += time.time() - start_time
            return result

        future = self._executor.submit(do_request)

        def on_request_done(_future, _request_wrapper=request_wrapper):
            self.response_queue.put((_request_wrapper, _future))

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

        self.pipeline.on_spider_started(self.spider)

        _callback_results = self.spider.start_requests()
        callback_results = []  # cumulative results from all callbacks
        request_or_item = None

        while True:
            if _callback_results:
                callback_results = itertools.chain(iter(_callback_results), callback_results)
                _callback_results = []

            future = None
            try:
                # use previously unused object or get a new one
                if request_or_item is None:
                    request_or_item = next(callback_results)  # request or item
            except StopIteration:
                pass
            else:
                if isinstance(request_or_item, RequestWrapper):
                    # try to schedule a request
                    future = self.downloader.enqueue_request(request_or_item)
                    if future is not None:
                        # the request was successfully enqueued - do not try again
                        request_or_item = None
                elif isinstance(request_or_item, Item):
                    self.pipeline.process_item(request_or_item, self.spider)
                    request_or_item = None
                    continue  # processing items is a priority
                else:
                    raise TypeError('Expected a Request or am Item instance')

            try:
                # if a request was successfully schedules do not wait much for an item
                # to take the next obj from callback ASAP
                timeout = 0.0 if future is not None else 0.01
                request_wrapper, future = self.downloader.response_queue.get(timeout=timeout)
            except queue.Empty:
                if not request_or_item and not self.downloader.get_unfinished_requests_count():
                    # no more scheduled requests and objects from callbacks
                    break  # the spider has finished its work
            else:
                exc = future.exception()
                if exc:
                    logger.error('There was an exception: %s\n%s',
                                 exc, '\n'.join(traceback.format_tb(exc.__traceback__)))
                    if request_wrapper.errback:
                        _callback_results = request_wrapper.errback(exc, request_wrapper)
                else:
                    if request_wrapper.callback:
                        response_wrapper = ResponseWrapper(
                            response=future.result(),
                            request_wrapper=request_wrapper)
                        _callback_results = request_wrapper.callback(response_wrapper)

        self.pipeline.on_spider_finished(self.spider)


class Spider():
    """Base spider.
    """
    start_urls = ()

    def start_requests(self):
        for url in self.start_urls:
            session = requests.Session()
            yield RequestWrapper(session, 'GET', url, callback=self.parse)

    def parse(self, response_wrapper):
        raise NotImplementedError('Override this method in your subclasses.')


class UrlFingerprints():

    def __init__(self):
        self.fingerprints = set()

    def add(self, url):
        """Add URL to the fingerprint store. Returns True if the URL fingerprint was successfully
        added. Return False if fingerprint if the URL is already in the store.
        """
        fingerprint = self._calculate_fingerprint(url)
        if fingerprint in self.fingerprints:
            return False
        self.fingerprints.add(fingerprint)
        return True

    def _calculate_fingerprint(self, url):
        return self._canonicalize_url(url)

    def _canonicalize_url(self, url, keep_blank_values=True, keep_fragments=False):
        """Canonicalize the given url.
        """
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
        query = urlparse.urlencode(sorted(urlparse.parse_qsl(query, keep_blank_values)))
        if not keep_fragments:
            fragment = ''
        return urlparse.urlunparse((scheme, netloc.lower(), path, params, query, fragment))


class RouteUrlFingerprints(UrlFingerprints):
    """
    """
    def _calculate_fingerprint(self, url):
        return urlparse.urlparse(url).path


class TrainsSpider(Spider):
    """Spider to scrape electrical train data from Yandex.
    """
    start_urls = ['http://m.rasp.yandex.ru/direction?city=213']

    def __init__(self, *args, **kwargs):
        super(TrainsSpider, self).__init__(*args, **kwargs)
        self.route_url_fps = RouteUrlFingerprints()

    def parse(self, response_wrapper):
        html_doc = response_wrapper.html_doc
        direction_nodes = html_doc.xpath('//div[@class="b-choose-geo"]/ul/li/a')
        for direction_node in direction_nodes:
            direction_url = direction_node.xpath('./@href')[0]
            if 'direction=_unknown' in direction_url:
                continue
            direction_url = urlparse.urljoin(response_wrapper.response.url, direction_url)
            # direction_name = direction_node.xpath('./text()')[0]
            # if 'горьковское' not in direction_name.lower():
            #     continue
            yield RequestWrapper(response_wrapper.session, 'GET', direction_url,
                                 callback=self.parse_direction)

    def parse_direction(self, response_wrapper):
        html_doc = response_wrapper.html_doc

        direction = html_doc.xpath('//select[@id="id_direction"]/option[@selected]')[0]
        direction_name = direction.xpath('./text()')[0]
        direction_id = direction.xpath('./@value')[0]

        stations = []
        station_nodes = html_doc.xpath('//select[@id="id_station_to"]/option')
        for station_no, station in enumerate(station_nodes):
            station_id = int(station.xpath('./@value')[0])
            if not station_id:
                continue  # separator
            station_name = station.xpath('./text()')[0]
            station_item = StationItem(
                direction_name=direction_name,
                direction_id=direction_id,
                station_name=station_name,
                station_id=station_id,
            )
            yield station_item
            stations.append((station_id, station_name))

        route_form = Form(response_wrapper, form_name='web')
        station_from_id, station_from_name = stations[0]
        route_form.fields['station_from'] = station_from_id
        route_form.fields['mode'] = 'all'
        for station_to_id, station_to_name in stations[1:]:
            if not station_to_id:
                continue
            route_form.fields['station_to'] = station_to_id
            # logger.info('%s -> %s', station_from_name, station_to_name)
            yield route_form.to_request(callback=self.parse_route)
            # return

    def parse_route(self, response_wrapper):
        html_doc = response_wrapper.html_doc
        for route_node in html_doc.xpath('//span[@class="time"]/a/@href'):
            route_url = str(route_node)
            route_url = urlparse.urljoin(response_wrapper.response.url, route_url)
            if self.route_url_fps.add(route_url):
                yield RouteItem(route_url=route_url)


class ItemPipeline():
    """Base item pipeline
    """
    def on_spider_started(self, spider):
        pass

    def on_spider_finished(self, spider):
        pass

    def process_item(self, item, spider):
        assert isinstance(item, Item)
        assert isinstance(spider, Spider)


class Item(dict):
    pass


class StationItem(Item):
    pass


class RouteItem(Item):
    pass


class TrainsPipeline(ItemPipeline):
    """
    """
    def __init__(self):
        self.item_count = 0

        Region.objects.all().delete()
        Direction.objects.all().delete()
        Station.objects.all().delete()

        self.moscow_region = Region.objects.create(id=215, name='Москва')

    def _process_station_item(self, item):
        print('Station: {direction_name}, {station_name} ({station_id})'.format(**item))

        direction = Direction.objects.filter(id=item['direction_id']).first()
        if direction is None:
            direction = Direction.objects.create(
                id=item['direction_id'], name=item['direction_name'], region=self.moscow_region)
        else:
            assert direction.name == item['direction_name'], '%r != %r' % (
                direction.name, item['direction_name'])

        station = Station.objects.filter(id=item['station_id']).first()
        if station is None:
            station = Station.objects.create(
                id=item['station_id'], name=item['station_name'])
        else:
            assert station.name == item['station_name'], '%r != %r' % (
                station.name, item['station_name'])
        station.directions.add(direction)

    def _process_route_item(self, item):
        print('Route: {route_url}'.format(**item))

    def process_item(self, item, spider):
        self.item_count += 1
        if isinstance(item, StationItem):
            self._process_station_item(item)
        elif isinstance(item, RouteItem):
            self._process_route_item(item)
        else:
            raise TypeError('Unsupported item type')

    def on_spider_finished(self, spider):
        pass


class Command(BaseCommand):

    help = ''

    def handle(self, **options):

        # make insertions faster
        connection.cursor().execute('PRAGMA journal_mode = MEMORY')
        connection.cursor().execute('PRAGMA locking_mode = EXCLUSIVE')

        downloader = Downloader(5, 0.0)
        pipeline = TrainsPipeline()
        spider_engine = SpiderEngine(
            spider=TrainsSpider(),
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
