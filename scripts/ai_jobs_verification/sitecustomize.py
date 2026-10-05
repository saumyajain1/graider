"""Opt-in SDK replacement for the constrained verification container only."""

import os

if os.environ.get("GRAIDER_VERIFY_FAKE_AI") == "true":
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from fake_provider import install

    install()
