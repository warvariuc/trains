__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from django.db import models
from django.contrib import admin
from django.contrib.admin.templatetags.admin_static import static
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.http import urlencode

from .models import Station, Direction, Region, Route, Schedule


def add_related_links(foreign_key_field):
    assert isinstance(
        foreign_key_field,
        models.fields.related.ReverseSingleRelatedObjectDescriptor)
    related_model = foreign_key_field.field.model
    foreign_key_field_name = foreign_key_field.field.name

    def decorator(cls):
        assert issubclass(cls, admin.ModelAdmin)
        reverse_path = "admin:%s_%s_" % (
            related_model._meta.app_label, related_model.__name__.lower())

        def links(self, instance):
            if instance.id is None:
                return ''
            links = []
            for related_obj in related_model.objects.filter(
                    **{foreign_key_field_name: instance.id}):
                url = reverse(reverse_path + 'change', args=(related_obj.id,))
                links.append('<a href="%s">%s</a>' % (url, related_obj))
            add_url = '%s?%s' % (reverse(reverse_path + 'add'),
                                 urlencode({foreign_key_field_name: instance.id}))
            links.append(
                '<a href="%s" class="add-another" title="%s">'
                '<img src="%s" width="10" height="10"/></a>'
                % (add_url, _('Add Another'), static('admin/img/icon_addlink.gif')))
            return mark_safe(' | '.join(links))

        links.allow_tags = True
        links.short_description = related_model._meta.verbose_name_plural
        readonly_field_name = 'related_objects_%s' % related_model.__name__
        setattr(cls, readonly_field_name, links)
        cls.readonly_fields = tuple(
            cls.readonly_fields) + (readonly_field_name,)
        return cls

    return decorator


@add_related_links(Direction.region)
class RegionAdmin(admin.ModelAdmin):
    pass


@add_related_links(Route.direction)
class DirectionAdmin(admin.ModelAdmin):
    pass


admin.site.register(Region, RegionAdmin)
admin.site.register(Direction, DirectionAdmin)
admin.site.register(Station)
admin.site.register(Route)
admin.site.register(Schedule)
