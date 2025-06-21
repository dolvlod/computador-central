# mi_app/urls.py

from django.urls import path
from . import views


urlpatterns = [
    path('', views.upload_raw_file, name='upload_raw_file'),
   # Cambiado a la nueva vista
    # path('', views.inicio, name='inicio'), 
]
