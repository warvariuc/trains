__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import requests

from .request import RequestWrapper


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
