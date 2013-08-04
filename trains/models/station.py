from django.db import models


class Station(models.Model):
    """Железнодорожная станция.
    """
    name = models.CharField(max_length=255, verbose_name='Наименование станции')
    yandex_id = models.IntegerField(verbose_name='Яндекс-индекс станции', unique=True)

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'станция'
        verbose_name_plural = 'станции'

    def __str__(self):
        return '%s' % self.name
