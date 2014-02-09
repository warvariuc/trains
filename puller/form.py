__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from urllib import parse as urlparse

from .request import RequestWrapper
from .response import ResponseWrapper


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
