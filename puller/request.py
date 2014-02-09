__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'


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
