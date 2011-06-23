# -*- coding: utf-8 -*-
"""
    templatetk.testsuite.bcinterp
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests the bytecode "interpreter".

    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
from __future__ import with_statement

from . import _basicexec

from .. import nodes
from ..bcinterp import run_bytecode, RuntimeState
from ..config import Config


class BCInterpTestCase(_basicexec.BasicExecTestCase):

    def get_exec_namespace(self, node, ctx, config):
        if ctx is None:
            ctx = {}
        if config is None:
            config = Config()
        rtstate = RuntimeState(ctx, config, 'dummy')
        return run_bytecode(node, '<dummy>'), rtstate

    def execute(self, node, ctx=None, config=None, info=None):
        ns, rtstate = self.get_exec_namespace(node, ctx, config)
        return ns['root'](rtstate)

    def evaluate(self, node, ctx=None, config=None, info=None):
        if config is None:
            config = Config()
        n = nodes
        node = n.Template(
            n.Assign(n.Name('__result__', 'store'), node), lineno=1
        ).set_config(config)
        ns, rtstate = self.get_exec_namespace(node, ctx, config)
        for event in ns['root'](rtstate):
            pass
        return rtstate.exported['__result__']


def suite():
    return _basicexec.make_suite(BCInterpTestCase, __name__)
