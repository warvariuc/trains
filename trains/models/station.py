from django.db import models

from . import Direction


class Station(models.Model):
    """Железнодорожная станция.
    """
    id = models.IntegerField(verbose_name='Яндекс-индекс станции', primary_key=True)
    name = models.CharField(max_length=255, verbose_name='Наименование станции')
    directions = models.ManyToManyField(Direction, related_name='stations')

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'станция'
        verbose_name_plural = 'станции'

    def __str__(self):
        return '%s' % self.name
