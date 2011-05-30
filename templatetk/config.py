# -*- coding: utf-8 -*-
"""
    templatetk.config
    ~~~~~~~~~~~~~~~~~

    Implements the compiler configuration object that is passed around
    the system.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""


class Undefined(object):
    # better object by default
    pass


class CompilerConfig(object):

    def __init__(self):
        self.sandboxed = False
        self.intercepted_binops = frozenset()
        self.intercepted_unops = frozenset()

    def get_autoescape_default(self, template_name):
        return False

    def getattr(self, object, attribute):
        # XXX: better defaults maybe
        try:
            return getattr(object, attribute)
        except AttributeError:
            try:
                return object[attribute]
            except (TypeError, LookupError):
                return Undefined()

    def getitem(self, object, attribute):
        return self.getattr(object, attribute)

    def get_filters(self):
        return {}

    def get_tests(self):
        return {}
