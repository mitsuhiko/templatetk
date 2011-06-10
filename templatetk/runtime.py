# -*- coding: utf-8 -*-
"""
    templatetk.runtime
    ~~~~~~~~~~~~~~~~~~

    Runtime helpers.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from .exceptions import BlockNotFoundException, BlockLevelOverflowException


class TemplateInterface(object):
    """A interface recommendation for template object implementations.
    This is not enforced anywhere in the system but the default
    implementation of the interpreter state follows this interface.
    """

    def generate_root(self, info):
        raise NotImplementedError()


class ContextView(object):
    """If one template includes another one and still wants to give read
    access to the variables from the other template this class can be
    passed there and give a view of the context of another frame.
    """

    def __init__(self, config):
        self.config = config

    def resolve_var(self, key):
        raise NotImplementedError('Cannot view context')

    def iter_vars(self):
        raise NotImplementedError('Cannot list variables')

    def __getitem__(self, key):
        rv = self.resolve_var(key)
        if self.config.is_undefined(rv):
            raise KeyError(key)
        return rv


class RuntimeInfo(object):
    """While the template engine is interpreting the ASTS or compiled
    code it has to keep a bunch of information around.  This does not
    keep the actual variables around, that is intepreter/compiled code
    dependent.
    """

    def __init__(self, config, template_name=None):
        self.config = config
        self.template_name = template_name
        self.autoescape = config.get_autoescape_default(template_name)
        self.volatile = False
        self.filters = config.get_filters()
        self.tests = config.get_tests()
        self.block_executers = {}
        self.template_cache = {}

    def get_template(self, template_name):
        """Gets a template from cache or if it's not there, it will newly
        load it and cache it.
        """
        template_name = self.config.join_path(self.template_name,
                                              template_name)

        if template_name in self.template_cache:
            return self.template_cache[template_name]
        rv = self.config.get_template(template_name)
        self.template_cache[template_name] = rv
        return rv

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

    def register_block(self, name, executor):
        self.block_executers.setdefault(name, []).append(executor)

    def evaluate_block(self, name, level=1, view=None):
        try:
            func = self.block_executers[name][level - 1]
        except KeyError:
            raise BlockNotFoundException(name)
        except IndexError:
            raise BlockLevelOverflowException(name, level)
        return func(self, view)

    def clone(self):
        rv = object.__new__(self.__class__)
        rv.__dict__.update(self.__dict__)
        rv.filters = dict(rv.filters)
        rv.tests = dict(rv.tests)
        rv.block_executers = dict(rv.block_executers)
        # rest stays shared.  XXX: better interface and cleaner semantics
        return rv

    def make_inheritance_info(self, template, template_name):
        rv = self.clone()
        return rv


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
