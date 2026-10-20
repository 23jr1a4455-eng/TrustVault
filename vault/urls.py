from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/<uuid:doc_id>/", views.document_detail, name="document_detail"),
    path("documents/<uuid:doc_id>/edit/", views.document_edit, name="document_edit"),
    path("documents/<uuid:doc_id>/delete/", views.document_delete, name="document_delete"),
]
