from django.urls import path
from .views import *

urlpatterns = [
    path("secure-media/<str:token>/", SecureMediaView.as_view(), name="secure_media"),
]