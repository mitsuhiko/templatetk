# -*- coding: utf-8 -*-
"""
    templatetk.config
    ~~~~~~~~~~~~~~~~~

    Implements the compiler configuration object that is passed around
    the system.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from types import MethodType, FunctionType

from .runtime import LoopContext, Function
from .utils import Markup


#: the types we support for context functions
_context_function_types = (FunctionType, MethodType)


class Undefined(object):
    # better object by default
    pass


class Config(object):

    def __init__(self):
        self.intercepted_binops = frozenset()
        self.intercepted_unops = frozenset()
        self.forloop_accessor = 'loop'
        self.forloop_parent_access = False
        self.strict_tuple_unpacking = False
        self.allow_noniter_unpacking = False
        self.markup_type = Markup

    def get_autoescape_default(self, template_name):
        return False

    def getattr(self, obj, attribute):
        # XXX: better defaults maybe
        try:
            return getattr(obj, str(attribute))
        except (UnicodeError, AttributeError):
            try:
                return obj[attribute]
            except (TypeError, LookupError):
                return Undefined()

    def getitem(self, obj, attribute):
        if isinstance(attribute, slice):
            # needed to support the legacy interface of the subscript op
            if attribute.step is None:
                return obj[attribute.start:attribute.stop]
            return obj[attribute]
        return self.getattr(obj, attribute)

    def to_unicode(self, obj):
        return unicode(obj)

    def is_undefined(self, obj):
        return isinstance(obj, Undefined)

    def undefined_variable(self, name):
        return Undefined()

    def is_context_function(self, obj):
        return isinstance(obj, _context_function_types) and \
               getattr(obj, 'contextfunction', False)

    def is_eval_context_function(self, obj):
        return isinstance(obj, _context_function_types) and \
               getattr(obj, 'evalcontextfunction', False)

    def get_filters(self):
        return {}

    def get_tests(self):
        return {}

    def wrap_loop(self, iterator, parent=None):
        return LoopContext(iterator)

    def join_path(self, parent, template_name):
        return template_name

    def get_template(self, template_name):
        raise NotImplementedError('Default config cannot load templates')

    def yield_from_template(self, template, info, view=None):
        raise NotImplementedError('Cannot yield from template objects')

    def iter_template_blocks(self, template):
        raise NotImplementedError('Cannot get blocks from template')

    def make_module(self, template_name, exports, body):
        raise NotImplementedError('Cannot create modules')

    def make_callout_context(self, info, lookup):
        raise NotImplementedError('Cannot create callout contexts')

    def callout_context_changes(self, callout_context):
        raise NotImplementedError('Cannot find callout context changes')

    def wrap_function(self, name, callable, arguments, defaults):
        return Function(self, name, callable, arguments, defaults)

    def resolve_from_import(self, module, attribute):
        return self.getattr(module, attribute)
