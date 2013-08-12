__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from django.contrib import admin
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _

from .models import Station, Direction, Region, Route, Schedule


# http://stackoverflow.com/questions/9919780
def add_link_field(target_model=None, field='', link_text=_('Редактировать')):

    def add_link(cls):
        reverse_name = target_model or cls.model.__name__.lower()

        def link(self, instance):
            app_name = instance._meta.app_label
            reverse_path = "admin:%s_%s_change" % (app_name, reverse_name)
            link_obj = getattr(instance, field, None) or instance
            url = reverse(reverse_path, args=(link_obj.id,))
            _link_text = link_text(link_obj) if callable(link_text) else link_text
            return mark_safe("<a href='%s'>%s</a>" % (url, _link_text))

        link.allow_tags = True
        link.short_description = reverse_name + ' link'
        cls.link = link
        cls.readonly_fields = list(getattr(cls, 'readonly_fields', [])) + ['link']
        return cls

    return add_link


@add_link_field()
class DirectionInline(admin.TabularInline):
    model = Direction
    fields = ['link']
    list_display = (lambda _: 'asdf',)
    can_delete = False


class RegionAdmin(admin.ModelAdmin):
    inlines = [DirectionInline]


admin.site.register(Region, RegionAdmin)
admin.site.register(Direction)
admin.site.register(Station)
admin.site.register(Route)
admin.site.register(Schedule)
