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


class JavaScriptWriter(object):

    def __init__(self, stream):
        self.stream_stack = [stream]

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
            if not self._first_write:
                stream.write('\n' * self._new_lines)
            self._first_write = False
            stream.write('  ' * self._indentation)
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

    def write_repr(self, obj):
        return self.write(json.dumps(obj))

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


def to_javascript(node, stream=None):
    """Converts a template to JavaScript."""
    if stream is None:
        stream = StringIO()
        as_string = True
    else:
        as_string = False
    gen = JavaScriptGenerator(stream, node.config)
    gen.visit(node, None)
    if as_string:
        return stream.getvalue()


class JavaScriptGenerator(NodeVisitor):

    def __init__(self, stream, config):
        NodeVisitor.__init__(self)
        self.config = config
        self.writer = JavaScriptWriter(stream)
        self.ident_manager = IdentManager()

    def begin_rtstate_func(self, name):
        self.writer.write_line('function %s(rtstate) {' % name)
        self.writer.indent()
        self.writer.write_line('var w = rtstate.write;')

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
            vars.append('%s = rtstate.lookup_var("%s")' % (
                target,
                sourcename
            ))

        # handle explicit var
        for name, local_id in fstate.local_identifiers.iteritems():
            if local_id not in already_handled:
                vars.append(local_id)

        self.writer.write_line('var %s;' % ', '.join(vars));

    def write_assign(self, target, expr, fstate):
        assert isinstance(target, nodes.Name), 'can only assign to names'
        name = fstate.lookup_name(target.name, 'store')
        self.writer.write_line('%s = ' % name)
        self.visit(expr, fstate)
        self.writer.write(';')
        if fstate.root:
            self.writer.write_line('rtstate.export_var("%s", %s);' % (
                target.name,
                name
            ))

    def visit_block(self, nodes, fstate):
        self.writer.write_newline()
        for node in nodes:
            self.visit(node, fstate)

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

        self.begin_rtstate_func('setup')
        self.writer.write_line('rt.registerBlockMapping(rtstate.info, blocks);')
        self.end_rtstate_func()

        for block_node in node.find_all(nodes.Block):
            block_fstate = fstate.derive(scope='hard')
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
            self.inject_scope_code(condition_fstate)
            self.writer.write_from_buffer(buffer)
            self.writer.outdent()
        else:
            else_ = []
        self.writer.write_line('}')

    def visit_Output(self, node, fstate):
        for child in node.nodes:
            self.writer.write_line('w(')
            self.visit(child, fstate)
            self.writer.write(');')

    def visit_Assign(self, node, fstate):
        self.writer.write_newline()
        self.write_assign(node.target, node.node, fstate)

    def visit_Name(self, node, fstate):
        name = fstate.lookup_name(node.name, node.ctx)
        self.writer.write(name)

    def visit_Const(self, node, fstate):
        self.writer.write_repr(node.value)
