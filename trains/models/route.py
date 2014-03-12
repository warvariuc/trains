from django.db import models

from . import Direction, Station


class Route(models.Model):
    """Маршрут.
    """
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255, help_text='Наименование маршрута')
    direction = models.ForeignKey(Direction, verbose_name='Направление маршрута')

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'маршрут'
        verbose_name_plural = 'маршруты'

    def __str__(self):
        return '%s' % self.name


class RouteStation(models.Model):
    """Станции маршрута.
    """
    route = models.ForeignKey(Route, verbose_name='Маршрут')
    station = models.ForeignKey(Station, verbose_name='Станция остановки')
    position = models.IntegerField(
        verbose_name='Порядковый номер',
        help_text='Порядковый номер станции в данном маршруте (первая станция имеет номер 0)')
    time = models.TimeField(
        null=True, blank=True,
        verbose_name='Время отправления',
        help_text='Пусто, если поезд здесь не останавливается')
    price = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='Стоимость проезда',
        help_text='Стоимость проезда в рублях: от первой станции маршрута до данной станции')

    class Meta:
        app_label = 'trains'
        verbose_name = 'станция маршрута'
        verbose_name_plural = 'станции маршрута'

    def __str__(self):
        return '%s: %s %s' % (self.route.name, self.station, self.time.strftime('%H:%M'))
