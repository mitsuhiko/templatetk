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

from templatetk.runtime import LoopContext


#: the types we support for context functions
_context_function_types = (FunctionType, MethodType)


class Undefined(object):
    # better object by default
    pass


class Config(object):

    def __init__(self):
        self.sandboxed = False
        self.intercepted_binops = frozenset()
        self.intercepted_unops = frozenset()
        self.forloop_accessor = 'loop'
        self.forloop_parent_access = False
        self.strict_tuple_unpacking = False

    def get_autoescape_default(self, template_name):
        return False

    def getattr(self, object, attribute):
        # XXX: better defaults maybe
        try:
            return getattr(object, str(attribute))
        except (UnicodeError, AttributeError):
            try:
                return object[attribute]
            except (TypeError, LookupError):
                return Undefined()

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

    def getitem(self, object, attribute):
        return self.getattr(object, attribute)

    def get_filters(self):
        return {}

    def get_tests(self):
        return {}

    def wrap_loop(self, iterator, parent=None):
        return LoopContext(iterator)
