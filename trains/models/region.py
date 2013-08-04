from django.db import models


class Region(models.Model):
    """Регион (Москва, Подольск, Ногинск, ...)
    """
    name = models.CharField(max_length=255, verbose_name='Наименование региона')

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'регион'
        verbose_name_plural = 'регионы'

    def __str__(self):
        return '%s' % self.name
