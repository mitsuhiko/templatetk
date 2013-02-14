# -*- coding: utf-8 -*-
"""
    templatetk.jscompiler
    ~~~~~~~~~~~~~~~~~~~~~

    This module can compile a node tree to JavaScript.  Not all that
    can be compiled to Python bytecode can also be compiled to JavaScript
    though.

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from StringIO import StringIO

from . import nodes
from .nodeutils import NodeVisitor
from .idtracking import IdentManager
from .fstate import FrameState
from .utils import json


class StopFrameCompilation(Exception):
    pass


class JavaScriptWriter(object):

    def __init__(self, stream, indentation=2):
        self.stream_stack = [stream]
        self.indentation = indentation

        self._new_lines = 0
        self._first_write = True
        self._indentation = 0

    def indent(self):
        self._indentation += 1

    def outdent(self, step=1):
        self._indentation -= step

    def write(self, x):
        """Write a string into the output stream."""
        stream = self.stream_stack[-1]
        if self._new_lines:
            if self.indentation >= 0:
                if not self._first_write:
                    stream.write('\n' * self._new_lines)
                self._first_write = False
                stream.write(' ' * (self.indentation * self._indentation))
            self._new_lines = 0
        if isinstance(x, unicode):
            x = x.encode('utf-8')
        stream.write(x)

    def write_newline(self, node=None, extra=0):
        self._new_lines = max(self._new_lines, 1 + extra)
        if node is not None and node.lineno != self._last_line:
            self._write_debug_info = node.lineno
            self._last_line = node.lineno

    def write_line(self, x, node=None, extra=0):
        self.write_newline(node, extra)
        self.write(x)

    def dump_object(self, obj):
        separators = None
        if self.indentation < 0:
            separators = (',', ':')
        return json.dumps(obj, separators=separators)

    def write_repr(self, obj):
        return self.write(self.dump_object(obj))

    def write_from_buffer(self, buffer):
        buffer.seek(0)
        while 1:
            chunk = buffer.read(4096)
            if not chunk:
                break
            self.stream_stack[-1].write(chunk)

    def start_buffering(self):
        new_stream = StringIO()
        self.stream_stack.append(new_stream)
        return new_stream

    def end_buffering(self):
        self.stream_stack.pop()


def to_javascript(node, stream=None, short_ids=False, indentation=2):
    """Converts a template to JavaScript."""
    if stream is None:
        stream = StringIO()
        as_string = True
    else:
        as_string = False
    gen = JavaScriptGenerator(stream, node.config, short_ids, indentation)
    gen.visit(node, None)
    if as_string:
        return stream.getvalue()


class JavaScriptGenerator(NodeVisitor):

    def __init__(self, stream, config, short_ids=False, indentation=2):
        NodeVisitor.__init__(self)
        self.config = config
        self.writer = JavaScriptWriter(stream, indentation)
        self.ident_manager = IdentManager(short_ids=short_ids)

    def begin_rtstate_func(self, name, with_writer=True):
        self.writer.write_line('function %s(rts) {' % name)
        self.writer.indent()
        if with_writer:
            self.writer.write_line('var w = rts.writeFunc;')

    def end_rtstate_func(self):
        self.writer.outdent()
        self.writer.write_line('}')

    def compile(self, node):
        assert isinstance(node, nodes.Template), 'can only transform ' \
            'templates, got %r' % node.__class__.__name__
        return self.visit(node, None)

    def write_scope_code(self, fstate):
        vars = []
        already_handled = set()
        for alias, old_name in fstate.required_aliases.iteritems():
            already_handled.add(alias)
            vars.append('%s = %s' % (alias, old_name))

        # at that point we know about the inner states and can see if any
        # of them need variables we do not have yet assigned and we have to
        # resolve for them.
        for target, sourcename in fstate.iter_required_lookups():
            already_handled.add(target)
            vars.append('%s = rts.lookupVar("%s")' % (
                target,
                sourcename
            ))

        # handle explicit var
        for name, local_id in fstate.local_identifiers.iteritems():
            if local_id not in already_handled:
                vars.append(local_id)

        if vars:
            self.writer.write_line('var %s;' % ', '.join(vars));

    def write_assign(self, target, expr, fstate):
        assert isinstance(target, nodes.Name), 'can only assign to names'
        name = fstate.lookup_name(target.name, 'store')
        self.writer.write_line('%s = ' % name)
        self.visit(expr, fstate)
        self.writer.write(';')
        if fstate.root:
            self.writer.write_line('rts.exportVar("%s", %s);' % (
                target.name,
                name
            ))

    def make_target_name_tuple(self, target):
        assert target.ctx in ('store', 'param')
        assert isinstance(target, (nodes.Name, nodes.Tuple))

        if isinstance(target, nodes.Name):
            return [target.name]

        def walk(obj):
            rv = []
            for node in obj.items:
                if isinstance(node, nodes.Name):
                    rv.append(node.name)
                elif isinstance(node, nodes.Tuple):
                    rv.append(walk(node))
                else:
                    assert 0, 'unsupported assignment to %r' % node
            return rv
        return walk(target)

    def write_assignment(self, node, fstate):
        rv = []
        def walk(obj):
            if isinstance(obj, nodes.Name):
                rv.append(fstate.lookup_name(obj.name, node.ctx))
                return
            for child in obj.items:
                walk(child)
        walk(node)
        self.writer.write(', '.join(rv))

    def write_context_as_object(self, fstate, reference_node):
        d = dict(fstate.iter_vars(reference_node))
        if not d:
            self.writer.write('rts.context')
            return
        self.writer.write('rts.makeOverlayContext({')
        for idx, (name, local_id) in enumerate(d.iteritems()):
            if idx:
                self.writer.write(', ')
            self.writer.write('%s: %s' % (self.writer.dump_object(name), local_id))
        self.writer.write('})')

    def start_buffering(self, fstate):
        self.writer.write_line('w = rts.startBuffering()')

    def return_buffer_contents(self, fstate, write_to_var=False):
        tmp = self.ident_manager.temporary()
        self.writer.write_line('var %s = rts.endBuffering();' % tmp)
        self.writer.write_line('w = %s[0];' % tmp)
        if write_to_var:
            self.writer.write_line('%s = %s[1];' % (tmp, tmp))
            return tmp
        else:
            self.writer.write_line('return %s[1];' % tmp)

    def visit_block(self, nodes, fstate):
        self.writer.write_newline()
        try:
            for node in nodes:
                self.visit(node, fstate)
        except StopFrameCompilation:
            pass

    def visit_Template(self, node, fstate):
        assert fstate is None, 'framestate passed to template visitor'
        fstate = FrameState(self.config, ident_manager=self.ident_manager,
                            root=True)
        fstate.analyze_identfiers(node.body)

        self.writer.write_line('(function(rt) {')
        self.writer.indent()

        self.begin_rtstate_func('root')
        buffer = self.writer.start_buffering()
        self.visit_block(node.body, fstate)
        self.writer.end_buffering()
        self.write_scope_code(fstate)
        self.writer.write_from_buffer(buffer)
        self.end_rtstate_func()

        self.begin_rtstate_func('setup', with_writer=False)
        self.writer.write_line('rt.registerBlockMapping(rts.info, blocks);')
        self.end_rtstate_func()

        for block_node in node.find_all(nodes.Block):
            block_fstate = fstate.derive(scope='hard')
            block_fstate.analyze_identfiers(block_node.body)
            self.begin_rtstate_func('block_' + block_node.name)
            buffer = self.writer.start_buffering()
            self.visit_block(block_node.body, block_fstate)
            self.writer.end_buffering()
            self.write_scope_code(block_fstate)
            self.writer.write_from_buffer(buffer)
            self.end_rtstate_func()

        self.writer.write_line('var blocks = {');
        for idx, block_node in enumerate(node.find_all(nodes.Block)):
            if idx:
                self.writer.write(', ')
            self.writer.write('"%s": block_%s' % (block_node.name,
                                                  block_node.name))
        self.writer.write('};')

        self.writer.write_line('return rt.makeTemplate(root, setup, blocks);')

        self.writer.outdent()
        self.writer.write_line('})')

    def visit_For(self, node, fstate):
        loop_fstate = fstate.derive()
        loop_fstate.analyze_identfiers([node.target], preassign=True)
        loop_fstate.add_special_identifier(self.config.forloop_accessor,
                                           preassign=True)
        if self.config.forloop_parent_access:
            fstate.add_implicit_lookup(self.config.forloop_accessor)
        loop_fstate.analyze_identfiers(node.body)

        loop_else_fstate = fstate.derive()
        if node.else_:
            loop_else_fstate.analyze_identfiers(node.else_)

        self.writer.write_line('rt.iterate(')
        self.visit(node.iter, loop_fstate)
        nt = self.make_target_name_tuple(node.target)
        self.writer.write(', ')
        if self.config.forloop_parent_access:
            self.visit(nodes.Name(self.config.forloop_accessor, 'load'), fstate)
        else:
            self.writer.write('null')
        self.writer.write(', %s, function(%s, ' % (
            self.writer.dump_object(nt),
            loop_fstate.lookup_name(self.config.forloop_accessor, 'store')
        ))
        self.write_assignment(node.target, loop_fstate)
        self.writer.write(') {')

        self.writer.indent()
        buffer = self.writer.start_buffering()
        self.visit_block(node.body, loop_fstate)
        self.writer.end_buffering()
        self.write_scope_code(loop_fstate)
        self.writer.write_from_buffer(buffer)
        self.writer.outdent()
        self.writer.write_line('}, ');

        if node.else_:
            self.writer.write('function() {')
            self.writer.indent()
            buffer = self.writer.start_buffering()
            self.visit_block(node.else_, loop_else_fstate)
            self.writer.end_buffering()
            self.write_scope_code(loop_else_fstate)
            self.writer.write_from_buffer(buffer)
            self.writer.outdent()
            self.writer.write('}')
        else:
            self.writer.write('null')

        self.writer.write(');')

    def visit_If(self, node, fstate):
        self.writer.write_line('if (')
        self.visit(node.test, fstate)
        self.writer.write(') { ')

        condition_fstate = fstate.derive()
        condition_fstate.analyze_identfiers(node.body)
        self.writer.indent()
        buffer = self.writer.start_buffering()
        self.visit_block(node.body, condition_fstate)
        self.writer.end_buffering()
        self.write_scope_code(condition_fstate)
        self.writer.write_from_buffer(buffer)
        self.writer.outdent()

        if node.else_:
            self.writer.write_line('} else {')
            self.writer.indent()
            condition_fstate_else = fstate.derive()
            condition_fstate_else.analyze_identfiers(node.else_)
            buffer = self.writer.start_buffering()
            self.visit_block(node.else_, condition_fstate_else)
            self.writer.end_buffering()
            self.write_scope_code(condition_fstate)
            self.writer.write_from_buffer(buffer)
            self.writer.outdent()
        else:
            else_ = []
        self.writer.write_line('}')

    def visit_Output(self, node, fstate):
        for child in node.nodes:
            self.writer.write_line('w(')
            if isinstance(child, nodes.TemplateData):
                self.writer.write_repr(child.data)
            else:
                self.writer.write('rts.info.finalize(')
                self.visit(child, fstate)
                self.writer.write(')')
            self.writer.write(');')

    def visit_Extends(self, node, fstate):
        self.writer.write_line('return rts.extendTemplate(')
        self.visit(node.template, fstate)
        self.writer.write(', ')
        self.write_context_as_object(fstate, node)
        self.writer.write(', w);')

        if fstate.root:
            raise StopFrameCompilation()

    def visit_Block(self, node, fstate):
        self.writer.write_line('rts.evaluateBlock("%s", ' % node.name)
        self.write_context_as_object(fstate, node)
        self.writer.write(');')

    def visit_Function(self, node, fstate):
        func_fstate = fstate.derive()
        func_fstate.analyze_identfiers(node.args)
        func_fstate.analyze_identfiers(node.body)

        argnames = [x.name for x in node.args]
        self.writer.write('rt.wrapFunction(')
        self.visit(node.name, fstate)
        self.writer.write(', %s, [' % self.writer.dump_object(argnames))

        for idx, arg in enumerate(node.defaults or ()):
            if idx:
                self.writer.write(', ')
            self.visit(arg, func_fstate)

        self.writer.write('], function(')

        for idx, arg in enumerate(node.args):
            if idx:
                self.writer.write(', ')
            self.visit(arg, func_fstate)

        self.writer.write(') {')
        self.writer.write_newline()
        self.writer.indent()

        buffer = self.writer.start_buffering()
        self.start_buffering(func_fstate)
        self.visit_block(node.body, func_fstate)
        self.writer.end_buffering()
        self.write_scope_code(func_fstate)
        self.writer.write_from_buffer(buffer)
        self.return_buffer_contents(func_fstate)

        self.writer.outdent()
        self.writer.write_line('})')

    def visit_Assign(self, node, fstate):
        self.writer.write_newline()
        self.write_assign(node.target, node.node, fstate)

    def visit_Name(self, node, fstate):
        name = fstate.lookup_name(node.name, node.ctx)
        self.writer.write(name)

    def visit_Const(self, node, fstate):
        self.writer.write_repr(node.value)

    def visit_Getattr(self, node, fstate):
        self.visit(node.node, fstate)
        self.writer.write('[')
        self.visit(node.attr, fstate)
        self.writer.write(']')

    def visit_Getitem(self, node, fstate):
        self.visit(node.node, fstate)
        self.writer.write('[')
        self.visit(node.arg, fstate)
        self.writer.write(']')

    def visit_Call(self, node, fstate):
        # XXX: For intercepting this it would be necessary to extract the
        # rightmost part of the dotted expression in node.node so that the
        # owner can be preserved for JavaScript (this)
        self.visit(node.node, fstate)
        self.writer.write('(')
        for idx, arg in enumerate(node.args):
            if idx:
                self.writer.write(', ')
            self.visit(arg, fstate)
        self.writer.write(')')

        if node.kwargs or node.dyn_args or node.dyn_kwargs:
            raise NotImplementedError('Dynamic calls or keyword arguments '
                                      'not available with javascript')

    def visit_TemplateData(self, node, fstate):
        self.writer.write('rt.markSafe(')
        self.writer.write_repr(node.data)
        self.writer.write(')')

    def visit_Tuple(self, node, fstate):
        raise NotImplementedError('Tuples not possible in JavaScript')

    def visit_List(self, node, fstate):
        self.writer.write('[')
        for idx, child in enumerate(node.items):
            if idx:
                self.writer.write(', ')
            self.visit(child, fstate)
        self.writer.write(']')

    def visit_Dict(self, node, fstate):
        self.writer.write('({')
        for idx, pair in enumerate(node.items):
            if idx:
                self.writer.write(', ')
            if not isinstance(pair.key, nodes.Const):
                raise NotImplementedError('Constant dict key required with javascript')
            # hack to have the same logic as json.dumps for keys
            self.writer.write(json.dumps({pair.key.value: 0})[1:-4] + ': ')
            self.visit(pair.value, fstate)
        self.writer.write('})')

    def visit_Filter(self, node, fstate):
        self.writer.write('rts.info.callFilter(')
        self.writer.write(', ')
        self.writer.write_repr(node.name)
        self.visit(node.node, fstate)
        self.writer.write(', [')
        for idx, arg in enumerate(node.args):
            if idx:
                self.writer.write(', ')
            self.visit(arg, fstate)
        self.writer.write('])')

        if node.kwargs or node.dyn_args or node.dyn_kwargs:
            raise NotImplementedError('Dynamic calls or keyword arguments '
                                      'not available with javascript')

    def visit_CondExpr(self, node, fstate):
        self.writer.write('(')
        self.visit(node.test, fstate)
        self.writer.write(' ? ')
        self.visit(node.true, fstate)
        self.writer.write(' : ')
        self.visit(node.false, fstate)
        self.writer.write(')')

    def visit_Slice(self, node, fstate):
        raise NotImplementedError('Slicing not possible with JavaScript')

    def binexpr(operator):
        def visitor(self, node, fstate):
            self.writer.write('(')
            self.visit(node.left, fstate)
            self.writer.write(' %s ' % operator)
            self.visit(node.right, fstate)
            self.writer.write(')')
        return visitor

    def visit_Concat(self, node, fstate):
        self.writer.write('rt.concat(rts.info, [')
        for idx, child in enumerate(node.nodes):
            if idx:
                self.writer.write(', ')
            self.visit(child, fstate)
        self.writer.write('])')

    visit_Add = binexpr('+')
    visit_Sub = binexpr('-')
    visit_Mul = binexpr('*')
    visit_Div = binexpr('/')
    visit_Mod = binexpr('%')
    del binexpr

    def visit_FloorDiv(self, node, fstate):
        self.writer.write('parseInt(')
        self.visit(node.left, fstate)
        self.writer.write(' / ')
        self.visit(node.right, fstate)
        self.writer.write(')')

    def visit_Pow(self, node, fstate):
        self.writer.write('Math.pow(')
        self.visit(node.left, fstate)
        self.writer.write(', ')
        self.visit(node.right, fstate)
        self.writer.write(')')

    def visit_And(self, node, fstate):
        self.writer.write('(')
        self.visit(node.left, fstate)
        self.writer.write(' && ')
        self.visit(node.right, fstate)
        self.writer.write(')')

    def visit_Or(self, node, fstate):
        self.writer.write('(')
        self.visit(node.left, fstate)
        self.writer.write(' || ')
        self.visit(node.right, fstate)
        self.writer.write(')')

    def visit_Not(self, node, fstate):
        self.writer.write('!(')
        self.visit(node.node, fstate)
        self.writer.write(')')
