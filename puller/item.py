__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'


class Item(dict):
    """
    """
    def __init__(self, **kwargs):
        dict.__init__(self, kwargs)
        # Alex Martelli's recipe
        self.__dict__ = self
