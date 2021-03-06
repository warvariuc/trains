__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import datetime

from django.db import models
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django import forms
from django.contrib.admin.templatetags.admin_static import static
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.http import urlencode

from .models import Station, Direction, Region, Route, RouteStation


def add_related_links(foreign_key_field):
    """
    """
    assert isinstance(foreign_key_field,
                      models.fields.related.ReverseSingleRelatedObjectDescriptor)
    related_model = foreign_key_field.field.model
    foreign_key_field_name = foreign_key_field.field.name

    def decorator(cls):
        assert issubclass(cls, admin.ModelAdmin)
        reverse_path = "admin:%s_%s_" % (
            related_model._meta.app_label, related_model._meta.module_name)

        def links(self, instance):
            if instance.id is None:
                return ''
            _links = []
            for related_obj in related_model.objects.filter(
                    **{foreign_key_field_name: instance.id}):
                related_obj_id = related_obj.id
                if isinstance(related_obj_id, str):
                    # hot fix for charfield primery keys containing '_'
                    # https://code.djangoproject.com/ticket/22266
                    related_obj_id = related_obj_id.replace('_', '_5F')
                url = reverse(reverse_path + 'change', args=(related_obj_id,))
                _links.append('<a href="%s">%s</a>' % (url, related_obj))
            add_url = '%s?%s' % (reverse(reverse_path + 'add'),
                                 urlencode({foreign_key_field_name: instance.id}))
            _links.append(
                '<a href="%s" class="add-another" title="%s">'
                '<img src="%s" width="10" height="10"/></a>'
                % (add_url, _('Add Another'), static('admin/img/icon_addlink.gif')))
            return mark_safe(' | '.join(_links))

        links.allow_tags = True
        links.short_description = related_model._meta.verbose_name_plural
        readonly_field_name = 'related_objects_%s' % related_model.__name__
        setattr(cls, readonly_field_name, links)
        cls.readonly_fields = tuple(cls.readonly_fields) + (readonly_field_name,)
        return cls

    return decorator


@add_related_links(Direction.region)
class RegionAdmin(admin.ModelAdmin):
    """
    """


@add_related_links(Route.direction)
class DirectionAdmin(admin.ModelAdmin):
    """
    """


class RouteStationInline(admin.TabularInline):
    model = RouteStation
    ordering = ['position']
    formfield_overrides = {
        models.TimeField: {'widget': forms.TimeInput(format='%H:%M')},
    }


class RouteStationsWidget(forms.Widget):

    class Media:
        js = (
            'js/jquery-2.1.0.min.js',
            'js/jquery-ui-1.10.4.min.js',
        )
        css = {'all': (
            'css/ui-lightness/jquery-ui-1.10.4.min.css',
            'css/trains.css',
        )}

    def render(self, name, value, attrs=None):
        return render_to_string("route_stations.html", {
            'route_stations': value,
            'name': name,
        })

    def value_from_datadict(self, data, files, name):
        return [dict(zip(('position', 'time', 'id', 'name'), value.split('|')))
                for value in data.getlist(name)]


class RouteStationsField(forms.Field):

    widget = RouteStationsWidget
    TIME_FORMAT = '%H:%M'
    default_error_messages = {
        'invalid_time': _('Неверное время "%(time)s" на станции "%(name)s".'),
        'time_required': _('Необходимо указать время на станции "%(name)s".'),
    }

    def prepare_value(self, value):
        if value is getattr(self, '_prepared_value', None):
            # this method is called multiple times - do not prepare the value again
            return value

        for route_station in value:

            if route_station['position'] is None:
                route_station['position'] = ''
            if route_station['time'] is None:
                route_station['time'] = ''
            elif isinstance(route_station['time'], datetime.time):
                route_station['time'] = route_station['time'].strftime(self.TIME_FORMAT)
            route_station['value'] = '{position}|{time}|{id}|{name}'.format_map(route_station)

        self._prepared_value = value  # save the prepared value
        return value

    def to_python(self, value):
        for route_station in value:
            if route_station['position'] == '':
                route_station['position'] = None
                route_station['time'] = ''  # remove time
            else:
                route_station['position'] = int(route_station['position'])
            if route_station['time'] == '':
                route_station['time'] = None
            else:
                try:
                    route_station['time'] = datetime.datetime.strptime(
                        route_station['time'], self.TIME_FORMAT).time()
                except ValueError:
                    raise ValidationError(self.error_messages['invalid_time'], 'invalid',
                                          route_station)
            route_station['id'] = int(route_station['id'])

        return value

    def validate(self, route_stations):
        super().validate(route_stations)
        station_count = 0
        for route_station in route_stations:
            if route_station['position'] is not None:
                assert route_station['position'] == station_count, 'Unexpected station order'
                station_count += 1
        if not station_count:
            return
        if route_stations[0]['time'] is None:
            raise ValidationError(self.error_messages['time_required'], 'required',
                                  route_stations[0])
        if route_stations[station_count - 1]['time'] is None:
            raise ValidationError(self.error_messages['time_required'], 'required',
                                  route_stations[station_count - 1])
        prev_time = None
        for route_station in route_stations[:station_count]:
            if route_station['time'] is None:
                continue
            if prev_time is not None:
                _dummy_date = datetime.date(2000, 1, 1)
                time_diff = (datetime.datetime.combine(_dummy_date, route_station['time']) -
                             datetime.datetime.combine(_dummy_date, prev_time)).total_seconds()
                if time_diff < 0:  # overflow to the next day?
                    time_diff += 24 * 60 * 60
                if time_diff == 0 or time_diff > 60 * 60:
                    raise ValidationError(self.error_messages['invalid_time'], '', route_station)
            prev_time = route_station['time']


class RouteForm(forms.ModelForm):
    """
    """
    route_stations = RouteStationsField(label=_("Станции"))

    class Meta(object):
        model = Route

    def __init__(self, *args, instance=None, **kwargs):
        route_stations = []
        if instance is not None:
            _route_stations = RouteStation.objects.filter(route=instance).order_by(
                'position').select_related('route', 'station')
            _route_station_ids = []
            for route_station in _route_stations:
                route_stations.append({
                    'id': route_station.station_id,
                    'name': route_station.station.name,
                    'position': route_station.position,
                    'time': route_station.time,
                })
                _route_station_ids.append(route_station.station_id)
            _direction_stations = Station.objects.filter(directions=instance.direction).exclude(
                id__in=_route_station_ids)
            for station in _direction_stations:
                route_stations.append({
                    'id': station.id,
                    'name': station.name,
                    'position': None,  # not in the route
                    'time': None,
            })

        initial = {'route_stations': route_stations}
        super().__init__(*args, instance=instance, initial=initial, **kwargs)

    def save(self, *args, **kwargs):
        RouteStation.objects.filter(route=self.instance).delete()
        _route_stations = []
        for route_station in self.cleaned_data['route_stations']:
            if route_station['position'] is None:
                break
            _route_stations.append(RouteStation(
                route=self.instance, station_id=route_station['id'],
                position=route_station['position'], time=route_station['time']))
        RouteStation.objects.bulk_create(_route_stations)
        return super().save(*args, **kwargs)


class RouteAdmin(admin.ModelAdmin):
    """
    """
    form = RouteForm


class RouteStationAdmin(admin.ModelAdmin):
    """
    """
    list_select_related = True


admin.site.register(Region, RegionAdmin)
admin.site.register(Direction, DirectionAdmin)
admin.site.register(Station)
admin.site.register(Route, RouteAdmin)
admin.site.register(RouteStation, RouteStationAdmin)
