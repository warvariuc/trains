__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

import json
import datetime

from django.db import models
from django.contrib import admin
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

    TIME_FORMAT = '%H:%M'
    # def __init__(self, *args, **kwargs):
    #     import ipdb; ipdb.set_trace()
    #     super().__init__(*args, **kwargs)
    # def value_from_datadict(self, data, files, name):

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
        for route_station in value:
            if route_station['position'] is None:
                route_station['position'] = ''
            route_station['time'] = (
                '' if route_station['time'] is None else
                route_station['time'].strftime(self.TIME_FORMAT))
            route_station['value'] = '{position}|{time}|{id}|{name}'.format_map(route_station)

        return render_to_string("route_stations.html", {
            'route_stations': value,
            'name': name,
        })

    def value_from_datadict(self, data, files, name):
        import ipdb; ipdb.set_trace()
        return data.get(name, None)


class RouteStationsField(forms.Field):
    widget = RouteStationsWidget

    def prepare_value(self, value):
        print('def prepare_value(self, value):')
        return value

    def to_python(self, value):
        return value


class RouteForm(forms.ModelForm):
    """Form configuring discount conditions and actions.
    """
    # route_stations = RouteStationsField(label=_("Станции"))
    route_stations = forms.Field(widget=RouteStationsWidget, label=_("Станции"))

    class Meta(object):
        model = Route

    def __init__(self, *args, instance=None, **kwargs):
        route_stations = []
        if instance is not None:
            _route_stations = RouteStation.objects.filter(
                route=instance).select_related('route', 'station')
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
