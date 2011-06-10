# -*- coding: utf-8 -*-
"""
    templatetk.utils
    ~~~~~~~~~~~~~~~~

    Various utilities

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from cgi import escape


class Markup(unicode):

    @classmethod
    def escape(cls, value):
        return cls(escape(value))

    def __html__(self):
        return self


class _Missing(object):
    __slots__ = ()

    def __repr__(self):
        return 'missing'

    def __reduce__(self):
        return 'missing'


missing = _Missing()
del _Missing
