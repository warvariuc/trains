import asyncio
import logging
import requests


logging.basicConfig(level='DEBUG')


class TrainsSpider():
    """Spider to scrape electrical train data from Yandex.
    """

    def __init__(self, start_url):
        self.start_url = start_url

    def _download(self, url):
        return requests.get(url)

    @asyncio.coroutine
    def start(self):
        response = yield from loop.run_in_executor(None, self._download, self.start_url)
        print(response)


loop = asyncio.get_event_loop()
# loop.call_soon(download, 'http://m.rasp.yandex.ru/direction?city=213')
# loop.run_forever()
start_urls = [
    'http://m.rasp.yandex.ru/direction?city=213',
    'https://google.com/1',
    'https://google.com/2',
    'https://google.com/3',
    'https://google.com/4',
    'https://google.com/5',
    'https://google.com/6',
]
tasks = [TrainsSpider(url).start() for url in start_urls]
loop.run_until_complete(asyncio.wait(tasks))
