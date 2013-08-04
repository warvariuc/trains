from django.db import models

from . import Direction, Station


class Route(models.Model):
    """Описание маршрута (рейса).
    """
    name = models.CharField(max_length=255, help_text='Наименование рейса')
    direction = models.ForeignKey(Direction, verbose_name='Направление рейса')

    class Meta:
        app_label = 'trains'
        ordering = ['name']
        verbose_name = 'маршрут'
        verbose_name_plural = 'маршруты'

    def __str__(self):
        return '%s' % self.name


class Schedule(models.Model):
    """Расписание движения поезда (рейс).
    """
    route = models.ForeignKey(Route, verbose_name='Маршрут')
    station = models.ForeignKey(Station, verbose_name='Станция остановки')
    position = models.IntegerField(
        verbose_name='Порядковый номер',
        help_text='Порядковый номер станции в данном маршруте (первая станция имеет номер 0)')
    time = models.TimeField(verbose_name='Время отправления')
    price = models.DecimalField(
        max_digits=6, decimal_places=2, verbose_name='Стоимость проезда',
        help_text='Стоимость проезда в рублях: от первой станции маршрута до данной станции')

    class Meta:
        app_label = 'trains'
        verbose_name = 'расписание'
        verbose_name_plural = 'расписания'
