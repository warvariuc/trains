__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from .models import Station, Direction, Region, Route, Schedule


class RelatedObjectsWidget(forms.widgets.Widget):
    """Widget showing links to related objects, considering there are not many
    of them
    """
    def render(self, name, value, attrs=None):
        import ipdb; from pprint import pprint; ipdb.set_trace()
        return mark_safe('<br/><b>Hello world!</b>')
        # model = target_model or cls.model
        # reverse_name = model.__name__.lower()
        # app_name = model._meta.app_label
        #
        # def link(self, instance):
        #     reverse_path = "admin:%s_%s_change" % (app_name, reverse_name)
        #     link_obj = getattr(instance, field, None) or instance
        #     url = reverse(reverse_path, args=(link_obj.id,))
        #     return mark_safe("<a href='%s'>%s</a>" % (url, _link_text))


class RegionForm(forms.ModelForm):
    related_objects = forms.Field(widget=RelatedObjectsWidget())
    class Meta:
        model = Region


admin.TabularInline
class RegionAdmin(admin.ModelAdmin):
    form = RegionForm


admin.site.register(Region, RegionAdmin)
admin.site.register(Direction)
admin.site.register(Station)
admin.site.register(Route)
admin.site.register(Schedule)
