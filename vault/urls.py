from django.urls import path

from . import views, views_admin

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/new/", views.document_upload, name="document_upload"),
    path("documents/trash/", views.document_trash, name="document_trash"),
    path("documents/<uuid:doc_id>/", views.document_detail, name="document_detail"),
    path("documents/<uuid:doc_id>/download/", views.document_download, name="document_download"),
    path("documents/<uuid:doc_id>/edit/", views.document_edit, name="document_edit"),
    path("documents/<uuid:doc_id>/delete/", views.document_delete, name="document_delete"),
    path("documents/<uuid:doc_id>/replace/", views.document_replace, name="document_replace"),
    path("documents/<uuid:doc_id>/restore/", views.document_restore, name="document_restore"),
    path("documents/<uuid:doc_id>/access/", views.document_access, name="document_access"),
    path("documents/<uuid:doc_id>/access/grant/", views.document_grant, name="document_grant"),
    path("documents/<uuid:doc_id>/access/<int:grant_id>/revoke/", views.document_revoke, name="document_revoke"),
    path("documents/<uuid:doc_id>/history/", views_admin.document_history, name="document_history"),
    path("activity/", views_admin.admin_activity, name="admin_activity"),
    path("activity/flags/", views_admin.admin_flags, name="admin_flags"),
    path("activity/verify/", views_admin.admin_verify, name="admin_verify"),
    path("users/", views_admin.admin_users, name="admin_users"),
    path("users/<int:user_id>/disable/", views_admin.admin_user_disable, name="admin_user_disable"),
    path("users/<int:user_id>/enable/", views_admin.admin_user_enable, name="admin_user_enable"),
]
