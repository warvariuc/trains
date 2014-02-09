__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from urllib import parse as urlparse


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
