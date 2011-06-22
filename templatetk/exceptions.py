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


class TemplateNotFound(TemplateException):

    def __init__(self, template_name):
        Exception.__init__(self)
        self.template_name = template_name


class TemplatesNotFound(TemplateNotFound):

    def __init__(self, template_names):
        TemplateNotFound.__init__(self, template_names[0])
        self.template_names = template_names


class BlockNotFoundException(TemplateException):
    pass


class BlockLevelOverflowException(TemplateException):
    pass
