from django.contrib.admin.apps import AdminConfig


class GraiderAdminConfig(AdminConfig):
    default_site = "config.admin.GraiderAdminSite"
