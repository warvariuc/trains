__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from .item import Item
from .spider import Spider


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
