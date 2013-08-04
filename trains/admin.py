__author__ = 'Victor Varvariuc <victor.varvariuc@gmail.com>'

from django.contrib import admin
from .models.station import Station
from .models.direction import Direction
from .models.region import Region
from .models.schedule import Route, Schedule


# class CustomerAdmin(admin.ModelAdmin):
#     list_display = ('__unicode__', 'email', 'date_of_birth', 'gender',
#                     'is_active', 'last_login', 'created_time', 'edited_time')
#     fields = ('last_name', 'first_name', 'middle_name', 'email',
#               'date_of_birth', 'gender', 'phone', 'mnogoru', 'sclub',
#               'is_active')
#     search_fields = ('last_name', 'first_name', 'middle_name', 'email',
#                      'gender', 'phone')
#     list_filter = ('is_active',)


admin.site.register(Region)
admin.site.register(Direction)
admin.site.register(Station)
admin.site.register(Route)
admin.site.register(Schedule)
