# -*- coding: utf-8 -*-
"""
    templatetk.exceptions
    ~~~~~~~~~~~~~~~~~~~~~

    Implements the public exception classes.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""


class TemplateException(Exception):
    pass


class BlockNotFoundException(TemplateException):
    pass


class BlockLevelOverflowException(TemplateException):
    pass
