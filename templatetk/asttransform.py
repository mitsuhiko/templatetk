# -*- coding: utf-8 -*-
"""
    templatetk.asttransform
    ~~~~~~~~~~~~~~~~~~~~~~~

    This module turns an ASTS into a regular Python ast for compilation.
    The generated AST is not a regular AST but will have all the template
    logic encapsulated in a function named 'root'.  If the ast is compiled
    and evaluated against a dictionary, that function can be cached::

        def compile_template(node):
            namespace = {}
            ast = to_ast(node, node.config)
            code = compile(ast, node.filename.encode('utf-8'), 'expr')
            exec code in namespace
            return namespace['root']

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from . import nodes
from .nodeutils import NodeVisitor
from .idtracking import IdentManager
from .fstate import FrameState


try:
    import ast
    have_ast = True
except ImportError:
    import _ast as ast
    have_ast = False


_context_target_map = {
    'store':        ast.Store,
    'param':        ast.Param,
    'load':         ast.Load
}


_cmpop_to_ast = {
    'eq':       ast.Eq,
    'ne':       ast.NotEq,
    'gt':       ast.Gt,
    'gteq':     ast.GtE,
    'lt':       ast.Lt,
    'lteq':     ast.LtE,
    'in':       ast.In,
    'notin':    ast.NotIn
}


def fix_missing_locations(node):
    """Adds missing locations so that the code becomes compilable
    by the Python interpreter.
    """
    def _fix(node, lineno, col_offset):
        if 'lineno' in node._attributes:
            if getattr(node, 'lineno', None) is None:
                node.lineno = lineno
            else:
                lineno = node.lineno
        if 'col_offset' in node._attributes:
            if getattr(node, 'col_offset', None) is None:
                node.col_offset = col_offset
            else:
                col_offset = node.col_offset
        for child in ast.iter_child_nodes(node):
            _fix(child, lineno, col_offset)
    _fix(node, 1, 0)
    return node


def to_ast(node):
    """Converts a template node to a python AST ready for compilation."""
    transformer = ASTTransformer(node.config)
    return transformer.transform(node)


class ASTTransformer(NodeVisitor):
    bcinterp_module = __name__.split('.')[0] + '.bcinterp'
    exception_module = __name__.split('.')[0] + '.exceptions'

    def __init__(self, config):
        NodeVisitor.__init__(self)
        if not have_ast:
            raise RuntimeError('Python 2.6 or later required for AST')
        self.config = config
        self.ident_manager = IdentManager()

    def transform(self, node):
        assert isinstance(node, nodes.Template), 'can only transform ' \
            'templates, got %r' % node.__class__.__name__
        return self.visit(node, None)

    def visit(self, node, state):
        rv = NodeVisitor.visit(self, node, state)
        assert rv is not None, 'visitor for %r failed' % node
        return rv

    def visit_block(self, nodes, state):
        result = []
        if nodes:
            for node in nodes:
                rv = self.visit(node, state)
                if isinstance(rv, ast.AST):
                    result.append(rv)
                else:
                    result.extend(rv)
        return result

    def make_getattr(self, dotted_name, lineno=None):
        parts = dotted_name.split('.')
        expr = ast.Name(parts.pop(0), ast.Load(), lineno=lineno)
        for part in parts:
            expr = ast.Attribute(expr, part, ast.Load())
        return expr

    def make_call(self, dotted_name, args, dyn_args=None, lineno=None):
        return ast.Call(self.make_getattr(dotted_name), args, [],
                        dyn_args, None, lineno=lineno)

    def make_rtstate_func(self, name, lineno=None):
        body = [ast.Assign([ast.Name('config', ast.Store())],
                           ast.Attribute(ast.Name('rtstate', ast.Load()),
                                         'config', ast.Load()))]
        funcargs = ast.arguments([ast.Name('rtstate', ast.Param())], None,
                                 None, [])
        return ast.FunctionDef(name, funcargs, body, [], lineno=lineno)

    def make_target_context(self, ctx):
        return _context_target_map[ctx]()

    def make_cmp_op(self, opname):
        return _cmpop_to_ast[opname]()

    def make_name_tuple(self, target_tuple, as_ast=True):
        assert isinstance(target_tuple, nodes.Tuple)
        assert target_tuple.ctx in ('store', 'param')
        def walk(obj):
            rv = []
            for node in obj.items:
                if isinstance(node, nodes.Name):
                    val = node.name
                    if as_ast:
                        val = ast.Str(val)
                    rv.append(val)
                elif isinstance(node, nodes.Tuple):
                    rv.append(walk(node))
                else:
                    assert 0, 'unsupported assignment to %r' % node
            if as_ast:
                return ast.Tuple(rv, ast.Load())
            return tuple(rv)
        return walk(target_tuple)

    def make_const(self, val, fstate):
        if isinstance(val, (int, float, long)):
            return ast.Num(val)
        elif isinstance(val, basestring):
            return ast.Str(val)
        elif isinstance(val, tuple):
            return ast.Tuple([self.make_const(x, fstate) for x in val],
                             ast.Load())
        elif isinstance(val, list):
            return ast.List([self.make_const(x, fstate) for x in val],
                            ast.Load())
        elif isinstance(val, dict):
            return ast.Dict([self.make_const(k, fstate) for k in val.keys()],
                            [self.make_const(v, fstate) for v in val.values()])
        elif val in (None, True, False):
            return ast.Name(str(val), ast.Load())
        assert 0, 'Unsupported constant value for compiler'

    def make_runtime_imports(self):
        yield ast.ImportFrom('__future__', [ast.alias('division', None)], 0)
        yield ast.ImportFrom(self.bcinterp_module,
                             [ast.alias('*', None)], 0)
        yield ast.ImportFrom(self.exception_module,
                             [ast.alias('*', None)], 0)

    def write_output(self, expr, fstate, lineno=None):
        if isinstance(expr, basestring):
            expr = ast.Str(unicode(expr))
        else:
            expr = self.make_call('rtstate.info.finalize', [expr])
        if fstate.buffer is None:
            expr = ast.Yield(expr)
        else:
            expr = ast.Call(ast.Attribute(ast.Name(fstate.buffer, ast.Load()),
                            'append', ast.Load()), [expr], [], None, None)
        return ast.Expr(expr, lineno=lineno)

    def make_resolve_call(self, node, fstate):
        args = [self.visit(x, fstate) for x in node.args]
        kwargs = [self.visit(x, fstate) for x in node.kwargs]
        dyn_args = dyn_kwargs = None
        if node.dyn_args is not None:
            dyn_args = self.visit(node.dyn_args, fstate)
        if node.dyn_kwargs is not None:
            dyn_kwargs = self.visit(node.dyn_kwargs, fstate)
        return ast.Call(ast.Name('resolve_call_args', ast.Load()),
                        args, kwargs, dyn_args, dyn_kwargs)

    def inject_scope_code(self, fstate, body):
        """This has to be called just before doing any modifications on the
        scoped code and after all inner frames were visisted.  This is required
        because the injected code will also need the knowledge of the inner
        frames to know which identifiers are required to lookup in the outer
        frame that the outer frame might not need.
        """
        before = []

        for alias, old_name in fstate.required_aliases.iteritems():
            before.append(ast.Assign([ast.Name(alias, ast.Store())],
                                      ast.Name(old_name, ast.Load())))
        for inner_func in fstate.inner_functions:
            before.extend(inner_func)

        # at that point we know about the inner states and can see if any
        # of them need variables we do not have yet assigned and we have to
        # resolve for them.
        for target, sourcename in fstate.iter_required_lookups():
            before.append(ast.Assign([ast.Name(target, ast.Store())],
                self.make_call('rtstate.lookup_var',
                               [ast.Str(sourcename)])))

        dummy_yield = []
        if fstate.buffer is None:
            dummy_yield.append(ast.If(ast.Num(0),
                [ast.Expr(ast.Yield(ast.Num(0)))], []))
        body[:] = before + body + dummy_yield

    def locals_to_dict(self, fstate, reference_node, lineno=None):
        keys = []
        values = []
        for name, local_id in fstate.iter_vars(reference_node):
            keys.append(ast.Str(name))
            values.append(ast.Name(local_id, ast.Load()))
        return ast.Dict(keys, values, lineno=lineno)

    def context_to_lookup(self, fstate, reference_node, lineno=None):
        locals = self.locals_to_dict(fstate, reference_node)
        if not locals.keys:
            return self.make_getattr('rtstate.context')
        return self.make_call('MultiMappingLookup',
            [ast.Tuple([locals, self.make_getattr('rtstate.context')],
                       ast.Load())], lineno=lineno)

    def make_assign(self, target, expr, fstate, lineno=None):
        assert isinstance(target, nodes.Name), 'can only assign to names'
        target_node = self.visit(target, fstate)
        rv = [ast.Assign([target_node], expr, lineno=lineno)]
        if fstate.root and isinstance(target_node, ast.Name):
            rv.append(ast.Expr(self.make_call('rtstate.export_var',
                                              [ast.Str(target.name),
                                               ast.Name(target_node.id,
                                                        ast.Load())])))
        return rv

    def make_template_lookup(self, template_expression, fstate):
        return [
            ast.Assign([ast.Name('template_name', ast.Store())],
                       self.visit(template_expression, fstate)),
            ast.Assign([ast.Name('template', ast.Store())],
                       self.make_call('rtstate.get_template',
                                      [ast.Name('template_name',
                                                ast.Load())]))
        ]

    def make_template_info(self, behavior):
        return ast.Assign([ast.Name('info', ast.Store())],
                           self.make_call('rtstate.info.make_info',
                                          [ast.Name('template', ast.Load()),
                                           ast.Name('template_name', ast.Load()),
                                           ast.Str(behavior)]))

    def make_template_generator(self, vars):
        return self.make_call('config.yield_from_template',
                              [ast.Name('template', ast.Load()),
                               ast.Name('info', ast.Load()),
                               vars])

    def make_template_render_call(self, vars, behavior):
        return [
            self.make_template_info(behavior),
            ast.For(ast.Name('event', ast.Store()),
                    self.make_template_generator(vars),
                    [ast.Expr(ast.Yield(ast.Name('event', ast.Load())))], [])
        ]

    def visit_Template(self, node, fstate):
        assert fstate is None, 'framestate passed to template visitor'
        fstate = FrameState(self.config, ident_manager=self.ident_manager,
                            root=True)
        fstate.analyze_identfiers(node.body)
        rv = ast.Module(lineno=1)
        root = self.make_rtstate_func('root')
        root.body.extend(self.visit_block(node.body, fstate))
        self.inject_scope_code(fstate, root.body)
        rv.body = list(self.make_runtime_imports()) + [root]

        setup = self.make_rtstate_func('setup')
        setup.body.append(ast.Expr(self.make_call('register_block_mapping',
            [self.make_getattr('rtstate.info'),
             ast.Name('blocks', ast.Load())])))

        blocks_keys = []
        blocks_values = []
        for block_node in node.find_all(nodes.Block):
            block_fstate = fstate.derive(scope='hard')
            block = self.make_rtstate_func('block_' + block_node.name)
            block.body.extend(self.visit_block(block_node.body, block_fstate))
            self.inject_scope_code(block_fstate, block.body)
            rv.body.append(block)
            blocks_keys.append(ast.Str(block_node.name))
            blocks_values.append(ast.Name('block_' + block_node.name,
                                          ast.Load()))

        rv.body.append(setup)
        rv.body.append(ast.Assign([ast.Name('blocks', ast.Store())],
                                  ast.Dict(blocks_keys, blocks_values)))

        return fix_missing_locations(rv)

    def visit_Output(self, node, fstate):
        rv = []
        for child in node.nodes:
            if isinstance(child, nodes.TemplateData):
                what = child.data
            else:
                what = self.visit(child, fstate)
            rv.append(self.write_output(what, fstate, lineno=child.lineno))
        return rv

    def visit_For(self, node, fstate):
        loop_fstate = fstate.derive()
        loop_fstate.analyze_identfiers([node.target], preassign=True)
        loop_fstate.add_special_identifier(self.config.forloop_accessor,
                                           preassign=True)
        if self.config.forloop_parent_access:
            fstate.add_implicit_lookup(self.config.forloop_accessor)
        loop_fstate.analyze_identfiers(node.body)

        body = []
        loop_else_fstate = fstate.derive()

        if node.else_:
            loop_else_fstate.analyze_identfiers(node.else_)
            did_not_iterate = self.ident_manager.temporary()
            body.append(ast.Assign([ast.Name(did_not_iterate, ast.Store())],
                                    ast.Num(0)))

        if (fstate.config.allow_noniter_unpacking or
            not fstate.config.strict_tuple_unpacking) and \
           isinstance(node.target, nodes.Tuple):
            iter_name = self.ident_manager.temporary()
            target = ast.Name(iter_name, ast.Store())
            body.append(ast.Assign([self.visit(node.target, loop_fstate)],
                ast.Call(ast.Name('lenient_unpack_helper', ast.Load()),
                         [ast.Name('config', ast.Load()),
                          ast.Name(iter_name, ast.Load()),
                          self.make_name_tuple(node.target)], [], None, None)))
        else:
            target = self.visit(node.target, loop_fstate)

        if self.config.forloop_parent_access:
            parent = self.visit(nodes.Name(self.config.forloop_accessor,
                                           'load'), fstate)
        else:
            parent = ast.Name('None', ast.Load())

        iter = self.visit(node.iter, fstate)
        wrapped_iter = self.make_call('config.wrap_loop', [iter, parent])

        loop_accessor = self.visit(nodes.Name(self.config.forloop_accessor,
                                              'store'), loop_fstate)
        tuple_target = ast.Tuple([target, loop_accessor], ast.Store())

        body.extend(self.visit_block(node.body, loop_fstate))
        self.inject_scope_code(loop_fstate, body)

        rv = [ast.For(tuple_target, wrapped_iter, body, [],
                      lineno=node.lineno)]

        if node.else_:
            rv.insert(0, ast.Assign([ast.Name(did_not_iterate, ast.Store())],
                                    ast.Num(1)))
            else_if = ast.If(ast.Name(did_not_iterate, ast.Load()), [], [])
            else_if.body.extend(self.visit_block(node.else_, loop_else_fstate))
            self.inject_scope_code(loop_fstate, else_if.body)
            rv.append(else_if)

        return rv

    def visit_Continue(self, node, fstate):
        return [ast.Continue(lineno=node.lineno)]

    def visit_Break(self, node, fstate):
        return [ast.Break(lineno=node.lineno)]

    def visit_If(self, node, fstate):
        test = self.visit(node.test, fstate)

        condition_fstate = fstate.derive()
        condition_fstate.analyze_identfiers(node.body)
        body = self.visit_block(node.body, condition_fstate)
        self.inject_scope_code(condition_fstate, body)

        if node.else_:
            condition_fstate_else = fstate.derive()
            condition_fstate_else.analyze_identfiers(node.else_)
            else_ = self.visit_block(node.else_, condition_fstate_else)
            self.inject_scope_code(condition_fstate, else_)
        else:
            else_ = []

        return [ast.If(test, body, else_)]

    def visit_ExprStmt(self, node, fstate):
        return ast.Expr(self.visit(node.node, fstate), lineno=node.lineno)

    def visit_Scope(self, node, fstate):
        scope_fstate = fstate.derive()
        scope_fstate.analyze_identfiers(node.body)
        rv = list(self.visit_block(node.body, scope_fstate))
        self.inject_scope_code(scope_fstate, rv)
        return rv

    def visit_FilterBlock(self, node, fstate):
        filter_fstate = fstate.derive()
        filter_fstate.analyze_identfiers(node.body)
        buffer_name = self.ident_manager.temporary()
        filter_fstate.buffer = buffer_name

        filter_args = self.make_resolve_call(node, filter_fstate)
        filter_call = self.make_call('rtstate.info.call_block_filter',
                                     [ast.Str(node.name),
                                      ast.Name(buffer_name, ast.Load())],
                                     filter_args)

        rv = list(self.visit_block(node.body, filter_fstate))
        rv = [ast.Assign([ast.Name(buffer_name, ast.Store())],
                          ast.List([], ast.Load()))] + rv + [
            self.write_output(filter_call, fstate),
            ast.Assign([ast.Name(buffer_name, ast.Store())],
                        ast.Name('None', ast.Load()))
        ]
        self.inject_scope_code(filter_fstate, rv)
        return rv

    def visit_Assign(self, node, fstate):
        # TODO: also allow assignments to tuples
        return self.make_assign(node.target, self.visit(node.node, fstate),
                                fstate, lineno=node.lineno)

    def visit_Import(self, node, fstate):
        vars = self.context_to_lookup(fstate, node)
        lookup = self.make_template_lookup(node.template, fstate)
        info = self.make_template_info('import')
        gen = self.make_template_generator(vars)
        module = self.make_call('info.make_module', [gen])
        rv = lookup + [info]
        rv.extend(self.make_assign(node.target, module, fstate,
                                   lineno=node.lineno))
        return rv

    def visit_FromImport(self, node, fstate):
        vars = self.context_to_lookup(fstate, node)
        lookup = self.make_template_lookup(node.template, fstate)
        info = self.make_template_info('import')
        gen = self.make_template_generator(vars)
        module = self.make_call('info.make_module', [gen])
        mod = self.ident_manager.temporary()
        rv = lookup + [info, ast.Assign([ast.Name(mod, ast.Store())], module)]
        for item in node.items:
            rv.extend(self.make_assign(item.target, self.make_call(
                'config.resolve_from_import',
                [module, self.visit(item.name, fstate)]), fstate,
                lineno=node.lineno))
        return rv

    def visit_Include(self, node, fstate):
        vars = self.context_to_lookup(fstate, node)
        lookup = self.make_template_lookup(node.template, fstate)
        render = self.make_template_render_call(vars, 'include')
        if node.ignore_missing:
            return ast.TryExcept(lookup, [ast.ExceptHandler(
                ast.Name('TemplateNotFound', ast.Load()), None,
                [ast.Pass()])], render)
        return lookup + render

    def visit_Extends(self, node, fstate):
        vars = self.context_to_lookup(fstate, node)
        lookup = self.make_template_lookup(node.template, fstate)
        render = self.make_template_render_call(vars, 'extends')
        return lookup + render + [ast.Return(None)]

    def visit_Block(self, node, fstate):
        block_name = ast.Str(node.name)
        vars = self.context_to_lookup(fstate, node)
        return ast.For(ast.Name('event', ast.Store()),
                       self.make_call('rtstate.evaluate_block',
                                      [block_name, vars]),
                       [ast.Expr(ast.Yield(ast.Name('event', ast.Load())))],
                       [], lineno=node.lineno)

    def visit_CallOut(self, node, fstate):
        callback = self.visit(node.callback, fstate)
        vars = self.context_to_lookup(fstate, node)
        ctx = self.make_call('rtstate.info.make_callout_context', [vars])
        ctxname = fstate.ident_manager.temporary()
        rv = [
            ast.Assign([ast.Name(ctxname, ast.Store())], ctx),
            ast.For(ast.Name('event', ast.Store()),
                      ast.Call(callback, [ast.Name(ctxname, ast.Load())], [],
                               None, None),
                      [self.write_output(ast.Name('event', ast.Load()),
                                         fstate)], [])
        ]
        for sourcename, local_id in fstate.local_identifiers.iteritems():
            rv.append(ast.Assign([ast.Name(local_id, ast.Store())],
                self.make_call('config.resolve_callout_var',
                    [ast.Name(ctxname, ast.Load()), ast.Str(sourcename)])))
        return rv

    def visit_Name(self, node, fstate):
        name = fstate.lookup_name(node.name, node.ctx)
        ctx = self.make_target_context(node.ctx)
        return ast.Name(name, ctx)

    def visit_Getattr(self, node, fstate):
        obj = self.visit(node.node, fstate)
        attr = self.visit(node.attr, fstate)
        return self.make_call('config.getattr', [obj, attr],
                              lineno=node.lineno)

    def visit_Getitem(self, node, fstate):
        obj = self.visit(node.node, fstate)
        arg = self.visit(node.arg, fstate)
        return self.make_call('config.getitem', [obj, arg],
                              lineno=node.lineno)

    def visit_Call(self, node, fstate):
        obj = self.visit(node.node, fstate)
        call_args = self.make_resolve_call(node, fstate)
        return self.make_call('rtstate.info.call', [obj], call_args,
                              lineno=node.lineno)

    def visit_Const(self, node, fstate):
        return self.make_const(node.value, fstate)

    def visit_TemplateData(self, node, fstate):
        return self.make_call('config.mark_safe', [ast.Str(node.data)],
                              lineno=node.lineno)

    def visit_Tuple(self, node, fstate):
        return ast.Tuple([self.visit(x, fstate) for x in node.items],
                         self.make_target_context(node.ctx))

    def visit_List(self, node, fstate):
        return ast.List([self.visit(x, fstate) for x in node.items],
                        ast.Load())

    def visit_Dict(self, node, fstate):
        keys = []
        values = []
        for pair in node.items:
            keys.append(self.visit(pair.key, fstate))
            values.append(self.visit(pair.value, fstate))
        return ast.Dict(keys, values, lineno=node.lineno)

    def visit_Filter(self, node, fstate):
        value = self.visit(node.node, fstate)
        filter_args = self.make_resolve_call(node, fstate)
        return self.make_call('rtstate.info.call_filter',
            [ast.Str(node.name), value], filter_args, lineno=node.lineno)

    def visit_CondExpr(self, node, fstate):
        test = self.visit(node.test, fstate)
        true = self.visit(node.true, fstate)
        false = self.visit(node.false, fstate)
        return ast.IfExp(test, true, false, lineno=node.lineno)

    def visit_MarkSafe(self, node, fstate):
        return self.make_call('config.mark_safe',
            [self.visit(node.expr, fstate)], lineno=node.lineno)

    def visit_MarkSafeIfAutoescape(self, node, fstate):
        value = self.visit(node.expr, fstate)
        return ast.IfExp(self.make_getattr('rtstate.info.autoescape'),
                         self.make_call('config.mark_safe', [value]),
                         value)

    def visit_Function(self, node, fstate):
        name = self.visit(node.name, fstate)
        defaults = ast.List([self.visit(x, fstate) for x in node.defaults],
                            ast.Load())
        arg_names = ast.Tuple([ast.Str(x.name) for x in node.args], ast.Load())
        buffer_name = self.ident_manager.temporary()
        func_fstate = fstate.derive()
        func_fstate.analyze_identfiers(node.args)
        func_fstate.analyze_identfiers(node.body)
        func_fstate.buffer = buffer_name

        internal_name = fstate.ident_manager.temporary()
        body = [ast.Assign([ast.Name(buffer_name, ast.Store())],
                           ast.List([], ast.Load()))]
        body.extend(self.visit_block(node.body, func_fstate))
        funcargs = ast.arguments([self.visit(x, func_fstate)
                                  for x in node.args], None, None, [])
        self.inject_scope_code(func_fstate, body)
        body.append(ast.Return(self.make_call('rtstate.info.concat_template_data',
            [ast.Name(buffer_name, ast.Load())])))

        # XXX: because inner_functions are prepended, the config alias is not
        # yet set up so we have to use rtstate.config.  Is that bad?  I mean,
        # it's certainly not beautiful, but not sure what a beautiful solution
        # would look like.
        fstate.inner_functions.append((
            ast.FunctionDef(internal_name, funcargs, body, [],
                            lineno=node.lineno),
            ast.Assign([ast.Name(internal_name, ast.Store())],
                       self.make_call('rtstate.config.wrap_function',
                       [name, ast.Name(internal_name, ast.Load()),
                        arg_names, defaults], lineno=node.lineno))
        ))
        return ast.Name(internal_name, ast.Load())

    def visit_Slice(self, node, fstate):
        start = self.visit(node.start, fstate)
        if node.stop is not None:
            stop = self.visit(node.stop, fstate)
        else:
            stop = self.Name('None', ast.Load())
        if node.step is not None:
            step = self.visit(node.step, fstate)
        else:
            stop = self.Name('None', ast.Load())
        return self.make_call('slice', [start, stop, step],
                              lineno=node.lineno)

    def binexpr(operator):
        def visitor(self, node, fstate):
            a = self.visit(node.left, fstate)
            b = self.visit(node.right, fstate)
            return ast.BinOp(a, operator(), b, lineno=node.lineno)
        return visitor

    def visit_Concat(self, node, fstate):
        arg = ast.List([self.visit(x, fstate) for x in node.nodes], ast.Load())
        return self.make_call('config.concat', [self.make_getattr('rtstate.info'), arg],
                              lineno=node.lineno)

    visit_Add = binexpr(ast.Add)
    visit_Sub = binexpr(ast.Sub)
    visit_Mul = binexpr(ast.Mult)
    visit_Div = binexpr(ast.Div)
    visit_FloorDiv = binexpr(ast.FloorDiv)
    visit_Mod = binexpr(ast.Mod)
    visit_Pow = binexpr(ast.Pow)
    del binexpr

    def visit_And(self, node, fstate):
        left = self.visit(node.left, fstate)
        right = self.visit(node.right, fstate)
        return ast.BoolOp(ast.And(), [left, right], lineno=node.lineno)

    def visit_Or(self, node, fstate):
        left = self.visit(node.left, fstate)
        right = self.visit(node.right, fstate)
        return ast.BoolOp(ast.Or(), [left, right], lineno=node.lineno)

    def visit_Compare(self, node, fstate):
        left = self.visit(node.expr, fstate)
        ops = []
        comparators = []
        for op in node.ops:
            ops.append(self.make_cmp_op(op.op))
            comparators.append(self.visit(op.expr, fstate))
        return ast.Compare(left, ops, comparators, lineno=node.lineno)

    def visit_Keyword(self, node, fstate):
        return ast.keyword(node.key, self.visit(node.value, fstate),
                           lineno=node.lineno)

    def unary(operator):
        def visitor(self, node, fstate):
            return ast.UnaryOp(operator(), self.visit(node.node, fstate),
                               lineno=node.lineno)
        return visitor

    visit_Pos = unary(ast.UAdd)
    visit_Neg = unary(ast.USub)
    visit_Not = unary(ast.Not)
    del unary
