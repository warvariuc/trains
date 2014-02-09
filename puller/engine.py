__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import itertools
import logging
import queue
import traceback

from .request import RequestWrapper
from .response import ResponseWrapper
from .spider import Spider
from .pipeline import ItemPipeline
from .downloader import Downloader
from .item import Item


logger = logging.getLogger(__name__)


class SpiderEngine():
    """
    """
    def __init__(self, spider, pipeline, downloader):
        assert isinstance(spider, Spider)
        assert isinstance(pipeline, ItemPipeline)
        assert isinstance(downloader, Downloader)
        self.spider = spider
        self.pipeline = pipeline
        self.downloader = downloader

    def start(self):
        logger.info('Starting puller engine')

        logger.info('Starting spider %r', self.spider.name)
        self.pipeline.on_spider_started(self.spider)

        _callback_results = self.spider.start_requests()
        callback_results = ()  # cumulative results from all callbacks
        request_or_item = None

        while True:
            if _callback_results:
                callback_results = itertools.chain(iter(_callback_results), callback_results)
                _callback_results = None

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

            # if a request was successfully scheduled do not wait much for an item
            # to take the next obj from callback ASAP
            timeout = 0.0 if future is not None else 0.01
            try:
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

        logger.info('Finishing spider %r', self.spider.name)
        self.pipeline.on_spider_finished(self.spider)
