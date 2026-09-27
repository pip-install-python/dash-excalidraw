/**
 * DeckBridge — a small, page-agnostic control surface for external drivers.
 *
 * Deck HQ (the owner's Stream Deck + XL plugin, ~/PycharmProjects/STREAMDECK)
 * drives Dash pages from outside the browser by running ONE JavaScript call in
 * the tab (AppleScript → Chrome). Instead of scraping the DOM, a page that
 * wants deck control publishes its controls here:
 *
 *   DeckBridge.update(path, fields, status)   // from a clientside callback
 *   DeckBridge.actions(path, {name: fn})      // once, from an asset
 *
 * and the deck calls, as a single JSON-in / JSON-out entry point:
 *
 *   DeckBridge.call('{"op":"state"}')
 *   DeckBridge.call('{"op":"step","field":"model","delta":1}')
 *   DeckBridge.call('{"op":"set","field":"seed","value":7}')
 *   DeckBridge.call('{"op":"act","name":"generate","args":{}}')
 *
 * Writes go through `dash_clientside.set_props`, so every existing callback
 * fires exactly as if the reader had changed the control by hand — the deck
 * never bypasses the page's own logic (model defaults, cost estimate, locks).
 *
 * Field shapes:
 *   {type:"select", id, value, options:[{value,label}], wrap?, disabled?}
 *   {type:"number", id, value, min, max, step, disabled?}
 *
 * Inert on pages that register nothing; costs nothing when no deck exists.
 */
(function () {
  if (window.DeckBridge) return;
  var B = (window.DeckBridge = { version: 1, pages: {}, _actions: {} });

  function page() {
    return B.pages[location.pathname] || null;
  }
  function setp(id, props) {
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props(id, props);
      return true;
    }
    return false;
  }
  function flat(opts) {
    var out = [];
    (opts || []).forEach(function (o) {
      if (o && o.items) out = out.concat(flat(o.items));
      else if (o && typeof o === "object") out.push({ value: o.value, label: o.label || String(o.value) });
      else if (o !== undefined && o !== null) out.push({ value: o, label: String(o) });
    });
    return out;
  }
  function describe(f) {
    if (!f) return null;
    if (f.type === "select") {
      var opts = flat(f.options);
      var i = -1;
      for (var k = 0; k < opts.length; k++) if (opts[k].value === f.value) i = k;
      return { type: "select", value: f.value, label: i >= 0 ? opts[i].label : String(f.value || "—"),
               index: i, count: opts.length, disabled: !!f.disabled };
    }
    return { type: "number", value: f.value, label: f.label || String(f.value), min: f.min, max: f.max,
             step: f.step, disabled: !!f.disabled };
  }

  B.update = function (path, fields, status) {
    var p = (B.pages[path] = B.pages[path] || { path: path });
    p.fields = fields || {};
    p.status = status || "";
    p.t = Date.now();
    return p.t;
  };
  B.actions = function (path, acts) {
    B._actions[path] = Object.assign(B._actions[path] || {}, acts || {});
  };

  B.state = function () {
    var p = page();
    if (!p) return { ok: false, page: location.pathname, err: "no deck controls on this page" };
    var fields = {};
    Object.keys(p.fields).forEach(function (k) { fields[k] = describe(p.fields[k]); });
    return { ok: true, page: p.path, fields: fields, status: p.status,
             actions: Object.keys(B._actions[p.path] || {}) };
  };

  B.set = function (field, value) {
    var p = page(), f = p && p.fields[field];
    if (!f) return { ok: false, err: "no field " + field };
    if (f.disabled) return { ok: false, err: field + " is disabled right now" };
    if (!setp(f.id, { value: value })) return { ok: false, err: "dash_clientside.set_props unavailable" };
    f.value = value;
    return { ok: true, field: field, now: describe(f) };
  };

  B.step = function (field, delta) {
    var p = page(), f = p && p.fields[field];
    if (!f) return { ok: false, err: "no field " + field };
    if (f.type === "select") {
      var opts = flat(f.options), n = opts.length;
      if (!n) return { ok: false, err: field + " has no options" };
      var i = -1;
      for (var k = 0; k < n; k++) if (opts[k].value === f.value) i = k;
      var j = f.wrap ? (((i + delta) % n) + n) % n : Math.max(0, Math.min(n - 1, i + delta));
      return B.set(field, opts[j].value);
    }
    var v = Number(f.value || 0) + delta * Number(f.step || 1);
    if (f.min !== undefined && f.min !== null) v = Math.max(Number(f.min), v);
    if (f.max !== undefined && f.max !== null) v = Math.min(Number(f.max), v);
    return B.set(field, v);
  };

  B.act = function (name, args) {
    var p = page();
    var fn = p && (B._actions[p.path] || {})[name];
    if (!fn) return { ok: false, err: "no action " + name + " on " + location.pathname };
    try {
      return Object.assign({ ok: true }, fn(args || {}) || {});
    } catch (e) {
      return { ok: false, err: String(e) };
    }
  };

  // The one entry point the deck uses: JSON string in, JSON string out.
  B.call = function (json) {
    var c = typeof json === "string" ? JSON.parse(json) : json;
    var r;
    if (c.op === "state") r = B.state();
    else if (c.op === "set") r = B.set(c.field, c.value);
    else if (c.op === "step") r = B.step(c.field, Number(c.delta || 0));
    else if (c.op === "act") r = B.act(c.name, c.args);
    else r = { ok: false, err: "unknown op " + c.op };
    if (r && r.ok && c.op !== "state") r.state = B.state();
    return JSON.stringify(r);
  };
})();
