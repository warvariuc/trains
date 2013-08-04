from django.db import models

from . import Region


class Direction(models.Model):
    """Направление (Белорусское, Горьковское, Рижское, ...)
    """
    name = models.CharField(max_length=255, verbose_name='Наименование направления')
    region = models.ForeignKey(Region)

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'направление'
        verbose_name_plural = 'направления'

    def __str__(self):
        return '%s' % self.name
