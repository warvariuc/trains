__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import requests
from lxml import html as lhtml

from .request import RequestWrapper


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
