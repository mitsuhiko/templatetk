# -*- coding: utf-8 -*-
"""
    templatetk.context
    ~~~~~~~~~~~~~~~~~~

    Implements a context object that is used by the interpreter.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from templatetk.utils import missing


class Context(object):
    """Data source at runtime for variables.  This is used for code that
    thinks it wants to modify the context at runtime in the compiled code.

    This is also used for the interpreter.
    """

    def __init__(self, config):
        self.config = config
        self._variables = {}
        self._stacked = []

        # TODO: track push state per level?  (if if if for, outer three not
        # modified, no need to copy).  Push dicts into stack alternatively?
        # TODO: timing
        self._needs_push = 0

    def push(self):
        self._needs_push = True

    def pop(self):
        if self._needs_push > 0:
            self._needs_push -= 1
        else:
            self._variables = self._stacked.pop()

    def __setitem__(self, key, value):
        if self._needs_push > 0:
            for x in xrange(self._needs_push):
                self._stacked.append(self._variables.copy())
            self._needs_push = 0
        self._variables[key] = value

    def __getitem__(self, key):
        return self._variables[key]

    def __contains__(self, key):
        return key in self._variables

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def resolve(self, key):
        rv = self._variables.get(key, missing)
        if rv is not missing:
            return rv
        return self.config.undefined_variable(key)

    def iteritems(self):
        return self._variables.iteritems()

    def iterkeys(self):
        return self._variables.iterkeys()
    __iter__ = iterkeys

    def itervalues(self):
        return self._variables.itervalues()

    def items(self):
        return list(self.iteritems())

    def keys(self):
        return list(self.iterkeys())

    def values(self):
        return list(self.itervalues())
