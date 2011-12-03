(function() {
  var global = this;
  var _templatetk = global.templatetk;
  var undefinedSingleton = [][0];

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

  function Markup(value) {
    this.value = value;
  }
  Markup.prototype = {
    toString : function() {
      return this.value;
    },
    toHTML : function() {
      return this;
    }
  };

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
      if (this.parent && typeof rv === 'undefined')
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

    renderToElements : function(context, selector) {
      var container = document.createElement('div');
      container.innerHTML = this.render(context);
      if (selector != null)
        return jQuery(selector, container)[0].childNodes;
      return container.childNodes;
    },

    renderInto : function(context, targetSelector, selector) {
      var elements = this.renderToElements(context, selector);
      jQuery(targetSelector).empty().append(elements);
    },

    replaceRender : function(context, selectors) {
      if (typeof selectors === 'string')
        this._replaceRender(context, selectors);
      for (var i = 0, n = selectors.length; i < n; i++)
        this._replaceRender(context, selectors[i]);
    },

    _replaceRender : function(context, selector) {
      var elements = this.renderToElements(context, selector);
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
      if (typeof level === 'undefined')
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
      if (this.autoescape)
        value = rtlib.escape(value);
      return '' + value;
    },

    registerBlock : function(name, executor) {
      var m = this.blockExecutors;
      (m[name] = (m[name] || [])).push(executor);
    },
  };

  var rtlib = {
    Markup : Markup,
    Template : Template,
    RuntimeState : RuntimeState,
    RuntimeInfo : RuntimeInfo,

    makeUndefined : function(value, name) {
      if (typeof value === 'undefined')
        return undefinedSingleton;
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
      if (typeof iterable.length !== 'undefined')
        return iterable;
      var rv = [];
      for (var obj in iterable)
        rv.push(obj);
      return rv;
    },

    unpackTuple : function(obj, unpackInfo, loopContext) {
      if (typeof obj.length !== 'undefined')
        return [obj];
      var rv = [loopContext];
      function unpack(obj, info) {
        for (var i = 0, n = info.length; i < n; i++)
          if (typeof info[i] == 'array')
            unpack(obj[i], info[i]);
          else
            rv.push(makeUndefined(obj[i], info[i]));
      }
      unpack(obj, unpackInfo);
      return rv;
    },

    markSafe : function(value) {
      return new Markup('' + value);
    },

    escape : function(value) {
      if (typeof value.toHTML !== 'undefined' &&
          Object.prototype.toString.call(value.toHTML) === '[object Function]')
        return value.toHTML();
      return escapeString(value);
    },

    iterate : function(iterable, parent, unpackInfo, func) {
      var index = 0;
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
    }
  };


  var lib = global.templatetk = {
    config : new Config(),
    globals : {},
    Config : Config,
    rt : rtlib,
    noConflict : function() {
      global.templatetk = _templatetk;
      return lib;
    }
  };
})();
