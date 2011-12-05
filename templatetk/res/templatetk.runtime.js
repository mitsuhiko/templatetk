(function(undefined) {
  var global = this;
  var _templatetk = global.templatetk;

  /* an aweful method to exploit the browser's support for escaping HTML */
  var _escapeMapping = {
    '&':    '&amp;',
    '>':    '&gt;',
    '<':    '&lt;',
    "'":    '&#39;',
    '"':    '&#34;'
  };
  function escapeString(value) {
    return ('' + value).replace(/(["'&<>])/g, function(match) {
      return _escapeMapping[match[0]];
    });
  }

  function Config() {
    this.filters = {};
  };
  Config.prototype = {
    getAutoEscapeDefault : function(templateName) {
      return true;
    },

    getFilters : function() {
      // TODO: make a copy here
      return this.filters;
    },

    evaluateTemplate : function(template, context, writeFunc, info) {
      template.run(template.makeRuntimeState(context, writeFunc, info));
    },

    getTemplate : function(name) {
      throw new Exception('Template loading not implemented');
    },

    joinPath : function(name, parent) {
      return name;
    }
  };

  function Context(vars, parent) {
    this.vars = vars;
    this.parent = parent;
  };
  Context.prototype = {
    lookup : function(name) {
      var rv = this.vars[name];
      if (this.parent && rv === undefined)
        return this.parent.lookup(name);
      return rtlib.makeUndefined(rv, name);
    }
  };

  function Template(rootFunc, setupFunc, blocks, config) {
    this.rootFunc = rootFunc;
    this.setupFunc = setupFunc;
    this.blocks = blocks;
    this.config = config;
    this.name = '<string>';
  };
  Template.prototype = {
    render : function(context) {
      context = new Context(context || {}, new Context(rtlib.getGlobals()));
      var buffer = [];
      var rtstate = this.makeRuntimeState(context, function(chunk) {
        buffer.push(chunk);
      });
      this.run(rtstate);
      return buffer.join("");
    },

    _resolveSelector : function(container, selector) {
      if (selector != null)
        return jQuery(selector, container)[0].childNodes;
      return container.childNodes;
    },

    renderToElements : function(context, selector) {
      var container = document.createElement('div');
      container.innerHTML = this.render(context);
      return this._resolveSelector(container, selector);
    },

    renderInto : function(context, targetSelector, selector) {
      var elements = this.renderToElements(context, selector);
      jQuery(targetSelector).empty().append(elements);
    },

    replaceRender : function(context, selectors) {
      var container = document.createElement('div');
      container.innerHTML = this.render(context);
      if (typeof selectors === 'string')
        this._replaceWithSelector(container, selectors);
      for (var i = 0, n = selectors.length; i < n; i++)
        this._replaceWithSelector(container, selectors[i]);
    },

    _replaceWithSelector : function(container, selector) {
      var elements = this._resolveSelector(container, selector);
      jQuery(selector).empty().append(elements);
    },

    makeRuntimeState : function(context, writeFunc, info) {
      return new rtlib.RuntimeState(context, writeFunc, this.config, this.name, info);
    },

    run : function(rtstate) {
      this.setupFunc(rtstate);
      this.rootFunc(rtstate);
    },

    toString : function() {
      if (this.name == null)
        return '[Template]';
      return '[Template "' + this.name + '"]';
    }
  };

  var RuntimeState = function(context, writeFunc, config, templateName, info) {
    this.context = context;
    this.config = config;
    this.writeFunc = writeFunc;
    if (!info)
      info = new rtlib.RuntimeInfo(this.config, templateName);
    this.info = info;
  };
  RuntimeState.prototype = {
    lookupVar : function(name) {
      return this.context.lookup(name);
    },

    makeOverlayContext : function(locals) {
      return new Context(locals, this.context);
    },

    evaluateBlock : function(name, context, level) {
      if (level === undefined)
        level = -1;
      return this.info.evaluateBlock(name, level, context, this.writeFunc);
    },

    exportVar : function(name, value) {
      this.info.exports[name] = value;
    },

    getTemplate : function(name) {
      var templateName = this.config.joinPath(name, this.templateName);
      var tmpl = this.info.templateCache[templateName];
      if (tmpl != null)
        return tmpl;
      var rv = this.config.getTemplate(templateName);
      this.info.templateCache[templateName] = rv;
      return rv;
    },

    extendTemplate : function(name, context) {
      var template = this.getTemplate(name);
      var info = this.info.makeInfo(template, name, "extends");
      return this.config.evaluateTemplate(template, context, this.writeFunc, info);
    }
  };

  var RuntimeInfo = function(config, templateName) {
    this.config = config;
    this.templateName = templateName;
    this.autoescape = config.getAutoEscapeDefault(templateName);
    this.filters = config.getFilters();
    this.blockExecutors = {};
    this.templateCache = {};
    this.exports = {};
  }
  RuntimeInfo.prototype = {
    evaluateBlock : function(name, level, vars, writeFunc) {
      var executors = this.blockExecutors[name];
      var func = executors[~level];
      return func(this, vars, writeFunc);
    },

    callFilter : function(filterName, obj, args) {
      var func = this.filters[filterName];
      return func.apply(obj, args);
    },

    makeInfo : function(template, templateName, behavior) {
      var rv = new RuntimeInfo(this.config, templateName);
      rv.templateCache = this.templateCache;
      if (behavior === 'extends')
        for (var key in this.blockExecutors)
          rv.blockExecutors[key] = this.blockExecutors[key];
      return rv;
    },

    finalize : function(value) {
      return rtlib.finalize(value, this.autoescape);
    },

    concatTemplateData : function(buffer) {
      var rv = buffer.join('');
      if (this.autoescape)
        rv = rtlib.markSafe(rv);
      return rv;
    },

    registerBlock : function(name, executor) {
      var m = this.blockExecutors;
      (m[name] = (m[name] || [])).push(executor);
    }
  };

  var rtlib = {
    Template : Template,
    RuntimeState : RuntimeState,
    RuntimeInfo : RuntimeInfo,

    makeUndefined : function(value, name) {
      return value;
    },

    getConfig : function() {
      return lib.config;
    },

    getGlobals : function() {
      return lib.globals;
    },

    registerBlockMapping : function(info, blocks) {
      for (var name in blocks)
        info.registerBlock(name, (function(renderFunc) {
          return function(info, vars, writeFunc) {
            return renderFunc(new rtlib.RuntimeState(vars, writeFunc, info.config,
              info.templateName));
          };
        })(blocks[name]));
    },

    makeTemplate : function(rootFunc, setupFunc, blocks) {
      return new this.Template(rootFunc, setupFunc, blocks, this.getConfig());
    },

    sequenceFromIterable : function(iterable) {
      if (!iterable)
        return [];
      if (iterable.length !== undefined)
        return iterable;
      return this.sequenceFromObject(iterable);
    },

    sequenceFromObject : function(obj) {
      var rv = [];
      for (var key in obj)
        rv.push(key);
      return rv;
    },

    unpackTuple : function(obj, unpackInfo, loopContext) {
      var rv = [null];
      function unpack(obj, info) {
        for (var i = 0, n = info.length; i < n; i++)
          if (typeof info[i] !== 'string')
            unpack(obj[i], info[i]);
          else
            rv.push(rtlib.makeUndefined(obj[i], info[i]));
      }
      unpack(obj, unpackInfo);
      return rv;
    },

    markSafe : function(value) {
      return value;
    },

    concat : function(info, pieces) {
      return ''.join(pieces);
    },

    finalize : function(value, autoescape) {
      return '' + value;
    },

    iterate : function(iterable, parent, unpackInfo, func, elseFunc) {
      var seq = rtlib.sequenceFromIterable(iterable);
      var n = seq.length;
      var ctx = {
        parent:     parent,
        first:      true,
        index0:     0,
        index:      1,
        revindex:   n,
        revindex0:  n - 1,
        cycle:      function() {
          return arguments[ctx.index0 % arguments.length];
        }
      };
      var simple = unpackInfo.length == 1 && typeof unpackInfo[0] === 'string';
      for (var i = 0; i < n; i++) {
        ctx.last = i + 1 == n;
        if (simple)
          func(ctx, rtlib.makeUndefined(seq[i], unpackInfo[0]));
        else
          func.apply(null, rtlib.unpackTuple(seq[i], unpackInfo, ctx));
        ctx.first = false;
        ctx.index0++, ctx.index++;
        ctx.revindex--, ctx.revindex0--;
      }
      if (ctx.index0 == 0 && elseFunc)
        elseFunc();
    },

    wrapFunction : function(name, argCount, defaults, func) {
      return func;
    }
  };


  var lib = global.templatetk = {
    config : new Config(),
    globals : {},
    Config : Config,
    rt : rtlib,
    utils : {
      escape : escapeString
    },
    noConflict : function() {
      global.templatetk = _templatetk;
      return lib;
    }
  };
})();
