__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import logging
from urllib import parse as urlparse
import time
import re

from django.core.management.base import BaseCommand
from django.db import connection
from django.db import transaction

import puller

from trains.models import Region, Direction, Station


logger = logging.getLogger(__name__)


class RouteUrlFingerprints(puller.UrlFingerprints):
    """Detect unique route URLs.
    """
    def _calculate_fingerprint(self, url):
        return urlparse.urlparse(url).path


class TrainsSpider(puller.Spider):
    """Spider to scrape electrical train data from Yandex.
    """
    name = 'Yandex electrical trains spider'
    start_urls = [
        'http://m.rasp.yandex.ru/direction?city=213',
    ]

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
            direction_name = direction_node.xpath('./text()')[0]
            if 'горьковское' not in direction_name.lower():
                continue
            yield puller.RequestWrapper(response_wrapper.session, 'GET', direction_url,
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

        route_form = puller.Form(response_wrapper, form_name='web')
        station_from_id, station_from_name = stations[0]
        route_form.fields['station_from'] = station_from_id
        route_form.fields['mode'] = 'all'
        for station_to_id, station_to_name in stations[1:]:
            if not station_to_id:
                continue
            route_form.fields['station_to'] = station_to_id
            # logger.info('%s -> %s', station_from_name, station_to_name)
            yield route_form.to_request(callback=self.parse_routes,
                                        meta={'direction_id': direction_id})
            return

    def parse_routes(self, response_wrapper):
        html_doc = response_wrapper.html_doc
        for route_url in html_doc.xpath('//span[@class="time"]/a/@href'):
            route_url = urlparse.urljoin(response_wrapper.response.url, str(route_url))
            if self.route_url_fps.add(route_url):
                yield puller.RequestWrapper(response_wrapper.session, 'GET', route_url,
                                            callback=self.parse_route,
                                            meta=response_wrapper.request_wrapper.meta)
                # return

    def parse_route(self, response_wrapper):
        html_doc = response_wrapper.html_doc
        route_url = response_wrapper.response.url
        route_id = re.search(r'^/thread/(.+)$', urlparse.urlparse(route_url).path).group(1)

        stations = []
        for station_node in html_doc.xpath('//div[@class="b-holster b-route-station"]/h4'):
            station_time = ''.join(station_node.xpath('./text()')).strip()
            try:
                station_time = re.search(r'.*(\d\d:\d\d|-)$', station_time).group(1)
            except AttributeError:
                print(station_time)
                raise
            station_url = station_node.xpath('./a/@href')[0]  # '/station/2000001/directions'
            station_id = re.search(r'^/station/(\d+)/directions$', station_url).group(1)
            station_url = urlparse.urljoin(route_url, station_url)
            stations.append((int(station_id), station_time, station_url))

        yield RouteItem(
            route_url=route_url,
            name=html_doc.xpath('//div[@class="b-holster"]/text()')[0].strip(),
            direction_id=response_wrapper.request_wrapper.meta['direction_id'],
            stations=stations,
        )


class StationItem(puller.Item):
    pass


class RouteItem(puller.Item):
    pass


class TrainsPipeline(puller.ItemPipeline):
    """
    """
    def __init__(self):
        # make insertions faster
        connection.cursor().execute('PRAGMA journal_mode = MEMORY')
        connection.cursor().execute('PRAGMA locking_mode = EXCLUSIVE')
        transaction.set_autocommit(False)

        Region.objects.all().delete()
        Direction.objects.all().delete()
        Station.objects.all().delete()

        self.moscow_region = Region.objects.create(id=215, name='Москва')

        self.item_count = 0

    def _process_station_item(self, item):
        print('Station item: {direction_name}, {station_name} ({station_id})'.format_map(item))

        direction = Direction.objects.filter(id=item.direction_id).first()
        if direction is None:
            direction = Direction.objects.create(
                id=item.direction_id, name=item.direction_name, region=self.moscow_region)
        else:
            assert direction.name == item.direction_name, '%r != %r' % (
                direction.name, item.direction_name)

        station = Station.objects.filter(id=item.station_id).first()
        if station is None:
            station = Station.objects.create(
                id=item.station_id, name=item.station_name)
        else:
            assert station.name == item.station_name, '%r != %r' % (
                station.name, item.station_name)
        station.directions.add(direction)

    def _process_route_item(self, item):
        import pprint
        print('Route item: {}'.format(pprint.pformat(item)))

    def process_item(self, item, spider):
        self.item_count += 1
        if isinstance(item, StationItem):
            self._process_station_item(item)
        elif isinstance(item, RouteItem):
            self._process_route_item(item)
        else:
            raise TypeError('Unsupported item type')

    def on_spider_finished(self, spider):
        transaction.commit()


class Command(BaseCommand):

    help = ''

    def handle(self, **options):

        downloader = puller.Downloader(max_workers=5, download_delay=0.0)
        pipeline = TrainsPipeline()
        spider_engine = puller.SpiderEngine(
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
