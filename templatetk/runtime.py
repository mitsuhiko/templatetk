# -*- coding: utf-8 -*-
"""
    templatetk.runtime
    ~~~~~~~~~~~~~~~~~~

    Runtime helpers.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""


class RuntimeInfo(object):
    """While the template engine is interpreting the ASTS or compiled
    code it has to keep a bunch of information around.  This does not
    keep the actual variables around, that is intepreter/compiled code
    dependent.
    """

    def __init__(self, config, template_name=None):
        self.config = config
        self.autoescape = config.get_autoescape_default(template_name)
        self.volatile = False
        self.filters = config.get_filters()
        self.tests = config.get_tests()
        self.block_executers = {}

    def save(self):
        return self.__dict__.copy()

    def revert(self, old):
        self.__dict__.clear()
        self.__dict__.update(old)

    def get_filter(self, name):
        try:
            return self.filters[name]
        except KeyError:
            raise RuntimeError('Filter %r not found' % name)

    def get_test(self, name):
        try:
            return self.tests[name]
        except KeyError:
            raise RuntimeError('Test %r not found' % name)

    def call_filter(self, name, obj, args, kwargs):
        func = self.get_filter(name)
        return func(obj, *args, **kwargs)

    def call_test(self, name, obj, args, kwargs):
        func = self.get_test(name)
        return func(obj, *args, **kwargs)


class LoopContextBase(object):
    """Base implementation for a loop context.  Solves most problems a
    loop context has to solve and implements the base interface that is
    required by the system.
    """

    def __init__(self, iterable):
        self._iterator = iter(iterable)
        self.index0 = -1

        # try to get the length of the iterable early.  This must be done
        # here because there are some broken iterators around where there
        # __len__ is the number of iterations left (i'm looking at your
        # listreverseiterator!).
        try:
            self._length = len(iterable)
        except (TypeError, AttributeError):
            self._length = None

    @property
    def length(self):
        if self._length is None:
            # if was not possible to get the length of the iterator when
            # the loop context was created (ie: iterating over a generator)
            # we have to convert the iterable into a sequence and use the
            # length of that.
            iterable = tuple(self._iterator)
            self._iterator = iter(iterable)
            self._length = len(iterable) + self.index0 + 1
        return self._length

    def __iter__(self):
        return LoopContextIterator(self)


class LoopContext(LoopContextBase):
    """A loop context for dynamic iteration.  This does not have to be used
    but it's a good base implementation.
    """

    def cycle(self, *args):
        """Cycles among the arguments with the current loop index."""
        if not args:
            raise TypeError('no items for cycling given')
        return args[self.index0 % len(args)]

    first = property(lambda x: x.index0 == 0)
    last = property(lambda x: x.index0 + 1 == x.length)
    index = property(lambda x: x.index0 + 1)
    revindex = property(lambda x: x.length - x.index0)
    revindex0 = property(lambda x: x.length - x.index)

    def __len__(self):
        return self.length

    def __repr__(self):
        return '<%s %r/%r>' % (
            self.__class__.__name__,
            self.index,
            self.length
        )


class LoopContextIterator(object):
    """The iterator for a loop context."""
    __slots__ = ('context',)

    def __init__(self, context):
        self.context = context

    def __iter__(self):
        return self

    def next(self):
        ctx = self.context
        ctx.index0 += 1
        return ctx._iterator.next(), ctx
