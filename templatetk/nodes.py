# -*- coding: utf-8 -*-
"""
    templatetk.nodes
    ~~~~~~~~~~~~~~~~

    Implements the AST of the templating language itself.  To avoid confusion
    in terms with the Python AST which is used for compilation, this is
    internally as ATST (Abstract Template Syntax Tree).

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import operator
from itertools import izip
from collections import deque


binop_to_func = {
    '*':        operator.mul,
    '/':        operator.truediv,
    '//':       operator.floordiv,
    '**':       operator.pow,
    '%':        operator.mod,
    '+':        operator.add,
    '-':        operator.sub
}

uaop_to_func = {
    'not':      operator.not_,
    '+':        operator.pos,
    '-':        operator.neg
}

cmpop_to_func = {
    'eq':       operator.eq,
    'ne':       operator.ne,
    'gt':       operator.gt,
    'gteq':     operator.ge,
    'lt':       operator.lt,
    'lteq':     operator.le,
    'in':       lambda a, b: a in b,
    'notin':    lambda a, b: a not in b
}


nodes_by_name = {}


class Impossible(Exception):
    """Raised if the node could not perform a requested action."""


class NodeType(type):
    """A metaclass for nodes that handles the field and attribute
    inheritance.  fields and attributes from the parent class are
    automatically forwarded to the child."""

    def __new__(cls, name, bases, d):
        newslots = []
        for attr in 'fields', 'attributes':
            names = d.get(attr, ())
            storage = []
            storage.extend(getattr(bases[0], attr, ()))
            storage.extend(names)
            assert len(bases) == 1, 'multiple inheritance not allowed'
            assert len(storage) == len(set(storage)), 'layout conflict'
            d[attr] = tuple(storage)
            newslots.extend(names)
        d.setdefault('abstract', False)
        d['__slots__'] = newslots
        rv = type.__new__(cls, name, bases, d)
        assert name not in nodes_by_name, 'Node naming conflict %r' % name
        nodes_by_name[name] = rv
        return rv


class Node(object):
    """Baseclass for all Jinja2 nodes.  There are a number of nodes available
    of different types.  There are three major types:

    -   :class:`Stmt`: statements
    -   :class:`Expr`: expressions
    -   :class:`Helper`: helper nodes
    -   :class:`Template`: the outermost wrapper node

    All nodes have fields and attributes.  Fields may be other nodes, lists,
    or arbitrary values.  Fields are passed to the constructor as regular
    positional arguments, attributes as keyword arguments.  Each node has
    two attributes: `lineno` (the line number of the node) and `config`.
    The `config` attribute is set at the end of the parsing process for
    all nodes automatically.
    """
    __metaclass__ = NodeType
    fields = ()
    attributes = ('lineno',)
    abstract = True

    def __init__(self, *fields, **attributes):
        if self.abstract:
            raise TypeError('abstract nodes are not instanciable')
        if fields:
            if len(fields) != len(self.fields):
                if not self.fields:
                    raise TypeError('%r takes 0 arguments' %
                                    self.__class__.__name__)
                raise TypeError('%r takes 0 or %d argument%s, got %d' % (
                    self.__class__.__name__,
                    len(self.fields),
                    len(self.fields) != 1 and 's' or '',
                    len(fields)
                ))
            for name, arg in izip(self.fields, fields):
                setattr(self, name, arg)
        for attr in self.attributes:
            setattr(self, attr, attributes.pop(attr, None))
        if attributes:
            raise TypeError('unknown attribute %r' %
                            iter(attributes).next())

    def iter_fields(self, exclude=None, only=None):
        """This method iterates over all fields that are defined and yields
        ``(key, value)`` tuples.  Per default all fields are returned, but
        it's possible to limit that to some fields by providing the `only`
        parameter or to exclude some using the `exclude` parameter.  Both
        should be sets or tuples of field names.
        """
        for name in self.fields:
            if (exclude is only is None) or \
               (exclude is not None and name not in exclude) or \
               (only is not None and name in only):
                try:
                    yield name, getattr(self, name)
                except AttributeError:
                    pass

    def iter_child_nodes(self, exclude=None, only=None):
        """Iterates over all direct child nodes of the node.  This iterates
        over all fields and yields the values of they are nodes.  If the value
        of a field is a list all the nodes in that list are returned.
        """
        for field, item in self.iter_fields(exclude, only):
            if isinstance(item, list):
                for n in item:
                    if isinstance(n, Node):
                        yield n
            elif isinstance(item, Node):
                yield item

    def find(self, node_type):
        """Find the first node of a given type.  If no such node exists the
        return value is `None`.
        """
        for result in self.find_all(node_type):
            return result

    def find_all(self, node_type):
        """Find all the nodes of a given type.  If the type is a tuple,
        the check is performed for any of the tuple items.
        """
        for child in self.iter_child_nodes():
            if isinstance(child, node_type):
                yield child
            for result in child.find_all(node_type):
                yield result

    def set_ctx(self, ctx):
        """Reset the context of a node and all child nodes.  Per default the
        parser will all generate nodes that have a 'load' context as it's the
        most common one.  This method is used in the parser to set assignment
        targets and other nodes to a store context.
        """
        todo = deque([self])
        while todo:
            node = todo.popleft()
            if 'ctx' in node.fields:
                node.ctx = ctx
            todo.extend(node.iter_child_nodes())
        return self

    def set_lineno(self, lineno, override=False):
        """Set the line numbers of the node and children."""
        todo = deque([self])
        while todo:
            node = todo.popleft()
            if 'lineno' in node.attributes:
                if node.lineno is None or override:
                    node.lineno = lineno
            todo.extend(node.iter_child_nodes())
        return self

    def set_config(self, config):
        """Set the config for all nodes."""
        todo = deque([self])
        while todo:
            node = todo.popleft()
            node.config = config
            todo.extend(node.iter_child_nodes())
        return self

    def __eq__(self, other):
        return type(self) is type(other) and \
               tuple(self.iter_fields()) == tuple(other.iter_fields())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            ', '.join('%s=%r' % (arg, getattr(self, arg, None)) for
                      arg in self.fields)
        )


class Stmt(Node):
    """Base node for all statements."""
    abstract = True


class Helper(Node):
    """Nodes that exist in a specific context only."""
    abstract = True


class Template(Node):
    """Node that represents a template.  This must be the outermost node that
    is passed to the compiler.
    """
    fields = ('body',)


class Output(Stmt):
    """A node that holds multiple expressions which are then printed out.
    This is used both for the `print` statement and the regular template data.
    """
    fields = ('nodes',)


class Extends(Stmt):
    """Represents an extends statement."""
    fields = ('template',)


class For(Stmt):
    """The for loop.  `target` is the target for the iteration (usually a
    :class:`Name` or :class:`Tuple`), `iter` the iterable.  `body` is a list
    of nodes that are used as loop-body, and `else_` a list of nodes for the
    `else` block.  If no else node exists it has to be an empty list.
    """
    fields = ('target', 'iter', 'body', 'else_')


class If(Stmt):
    """If `test` is true, `body` is rendered, else `else_`."""
    fields = ('test', 'body', 'else_')


class Function(Stmt):
    """Defines a function and stores it in the given target.
    """
    # TODO: can we define this as an expression with this new compiler?
    # Would make things a lot easier for everything but compilation ...
    fields = ('target', 'args', 'defaults', 'body')


class FilterBlock(Stmt):
    """Node for filter sections."""
    fields = ('body', 'name', 'args', 'kwargs', 'dyn_args', 'dyn_kwargs')


class Block(Stmt):
    """A node that represents a block."""
    fields = ('name', 'body')


class Include(Stmt):
    """A node that represents the include tag."""
    fields = ('template', 'with_context', 'ignore_missing')


class Import(Stmt):
    """A node that represents the import tag."""
    fields = ('template', 'target', 'with_context')


class FromImport(Stmt):
    """A node that represents the from import tag.  It's important to not
    pass unsafe names to the name attribute.  The compiler translates the
    attribute lookups directly into getattr calls and does *not* use the
    subscript callback of the interface.  As exported variables may not
    start with double underscores (which the parser asserts) this is not a
    problem for regular Jinja code, but if this node is used in an extension
    extra care must be taken.

    The list of names may contain tuples if aliases are wanted.
    """
    fields = ('template', 'names', 'with_context')


class ExprStmt(Stmt):
    """A statement that evaluates an expression and discards the result."""
    fields = ('node',)


class Assign(Stmt):
    """Assigns an expression to a target."""
    fields = ('target', 'node')


class Expr(Node):
    """Baseclass for all expressions."""
    abstract = True

    def can_assign(self):
        """Check if it's possible to assign something to this node."""
        return False


class BinExpr(Expr):
    """Baseclass for all binary expressions."""
    fields = ('left', 'right')
    operator = None
    abstract = True


class UnaryExpr(Expr):
    """Baseclass for all unary expressions."""
    fields = ('node',)
    operator = None
    abstract = True


class Name(Expr):
    """Looks up a name or stores a value in a name.
    The `ctx` of the node can be one of the following values:

    -   `store`: store a value in the name
    -   `load`: load that name
    -   `param`: like `store` but if the name was defined as function parameter.
    """
    fields = ('name', 'ctx')

    def can_assign(self):
        if self.ctx != 'store':
            return False
        return self.name not in ('true', 'false', 'none',
                                 'True', 'False', 'None')


class Literal(Expr):
    """Baseclass for literals."""
    abstract = True


class Const(Literal):
    """All constant values.  The parser will return this node for simple
    constants such as ``42`` or ``"foo"`` but it can be used to store more
    complex values such as lists too.  Only constants with a safe
    representation (objects where ``eval(repr(x)) == x`` is true).
    """
    fields = ('value',)


class TemplateData(Literal):
    """A constant template string."""
    fields = ('data',)


class Tuple(Literal):
    """For loop unpacking and some other things like multiple arguments
    for subscripts.  Like for :class:`Name` `ctx` specifies if the tuple
    is used for loading the names or storing.
    """
    fields = ('items', 'ctx')

    def can_assign(self):
        if self.ctx != 'store':
            return False
        for item in self.items:
            if not item.can_assign():
                return False
        return True


class List(Literal):
    """Any list literal such as ``[1, 2, 3]``"""
    fields = ('items',)


class Dict(Literal):
    """Any dict literal such as ``{1: 2, 3: 4}``.  The items must be a list of
    :class:`Pair` nodes.
    """
    fields = ('items',)


class Pair(Helper):
    """A key, value pair for dicts."""
    fields = ('key', 'value')


class Keyword(Helper):
    """A key, value pair for keyword arguments where key is a string."""
    fields = ('key', 'value')


class CondExpr(Expr):
    """A conditional expression (inline if expression).  (``{{
    foo if bar else baz }}``)
    """
    fields = ('test', 'true', 'false')


class Filter(Expr):
    """This node applies a filter on an expression.  `name` is the name of
    the filter, the rest of the fields are the same as for :class:`Call`.

    If the `node` of a filter is `None` the contents of the last buffer are
    filtered.  Buffers are created by macros and filter blocks.
    """
    fields = ('node', 'name', 'args', 'kwargs', 'dyn_args', 'dyn_kwargs')


class Test(Expr):
    """Applies a test on an expression.  `name` is the name of the test, the
    rest of the fields are the same as for :class:`Call`.
    """
    fields = ('node', 'name', 'args', 'kwargs', 'dyn_args', 'dyn_kwargs')


class Call(Expr):
    """Calls an expression.  `args` is a list of arguments, `kwargs` a list
    of keyword arguments (list of :class:`Keyword` nodes), and `dyn_args`
    and `dyn_kwargs` has to be either `None` or a node that is used as
    node for dynamic positional (``*args``) or keyword (``**kwargs``)
    arguments.
    """
    fields = ('node', 'args', 'kwargs', 'dyn_args', 'dyn_kwargs')


class Getitem(Expr):
    """Get an attribute or item from an expression and prefer the item."""
    fields = ('node', 'arg', 'ctx')

    def can_assign(self):
        return False


class Getattr(Expr):
    """Get an attribute or item from an expression that is a ascii-only
    bytestring and prefer the attribute.
    """
    fields = ('node', 'attr', 'ctx')

    def can_assign(self):
        return False


class Slice(Expr):
    """Represents a slice object.  This must only be used as argument for
    :class:`Getitem`.
    """
    fields = ('start', 'stop', 'step')


class Concat(Expr):
    """Concatenates the list of expressions provided after converting them to
    unicode.
    """
    fields = ('nodes',)


class Compare(Expr):
    """Compares an expression with some other expressions.  `ops` must be a
    list of :class:`Operand`\s.
    """
    fields = ('expr', 'ops')


class Operand(Helper):
    """Holds an operator and an expression."""
    fields = ('op', 'expr')

if __debug__:
    Operand.__doc__ += '\nThe following operators are available: ' + \
        ', '.join(sorted('``%s``' % x for x in set(binop_to_func) |
                  set(uaop_to_func) | set(cmpop_to_func)))


class Mul(BinExpr):
    """Multiplies the left with the right node."""
    operator = '*'


class Div(BinExpr):
    """Divides the left by the right node."""
    operator = '/'


class FloorDiv(BinExpr):
    """Divides the left by the right node and truncates conver the
    result into an integer by truncating.
    """
    operator = '//'


class Add(BinExpr):
    """Add the left to the right node."""
    operator = '+'


class Sub(BinExpr):
    """Substract the right from the left node."""
    operator = '-'


class Mod(BinExpr):
    """Left modulo right."""
    operator = '%'


class Pow(BinExpr):
    """Left to the power of right."""
    operator = '**'


class And(BinExpr):
    """Short circuited AND."""
    operator = 'and'


class Or(BinExpr):
    """Short circuited OR."""
    operator = 'or'


class Not(UnaryExpr):
    """Negate the expression."""
    operator = 'not'


class Neg(UnaryExpr):
    """Make the expression negative."""
    operator = '-'


class Pos(UnaryExpr):
    """Make the expression positive (noop for most expressions)"""
    operator = '+'


class MarkSafe(Expr):
    """Mark the wrapped expression as safe (wrap it as `Markup`)."""
    fields = ('expr',)


class MarkSafeIfAutoescape(Expr):
    """Mark the wrapped expression as safe (wrap it as `Markup`) but
    only if autoescaping is active.
    """
    fields = ('expr',)


class Continue(Stmt):
    """Continue a loop."""


class Break(Stmt):
    """Break a loop."""


class Scope(Stmt):
    """An artificial scope."""
    fields = ('body',)


# make sure nobody creates custom nodes
def _failing_new(*args, **kwargs):
    raise TypeError('can\'t create custom node types')
NodeType.__new__ = staticmethod(_failing_new); del _failing_new
