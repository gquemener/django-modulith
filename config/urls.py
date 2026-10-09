from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from modules.ticketing.presentation.views import home

urlpatterns = [
    path("", home, name="home"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("tickets/", include("modules.ticketing.presentation.urls")),
    path("admin/", admin.site.urls),
]
