#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    django_template_debug
    ~~~~~~~~~~~~~~~~~~~~~

    Hackery with django templates without having to have a whole django
    project.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from django.conf import settings
try:
    settings.configure(TEMPLATE_DEBUG=True)
except RuntimeError:
    # reload hackery
    pass

from django import template


def parse_template(source):
    return template.Template(source)


def render_template(source, *args, **kwargs):
    ctx = template.Context(dict(*args, **kwargs))
    return parse_template(source).render(ctx)
