/**
 * /ai-agent's deck actions — what a Stream Deck key can ask this page to do.
 * Fields (provider, model, effort, max_tokens, seed, timeline, scene) are
 * published by the page's mirror callback; see assets/deck_bridge.js.
 *
 *   generate · stop · clear · save · replay · end
 *   focus_prompt                     caret to the end of the prompt (then dictate)
 *   set_prompt {text, focus}
 *   append_prompt {text, sep}
 *   preset {name, prompt, style, provider, model, effort, max_tokens, focus}
 *
 * A preset changes provider → model → effort/budget with pauses between,
 * because each step fires the page's own server callbacks and the model
 * change RESETS effort and budget to that model's defaults. Setting all three
 * at once would be overwritten by those callbacks a moment later.
 */
(function () {
  var PATH = "/ai-agent";

  function sp(id, props) {
    window.dash_clientside.set_props(id, props);
  }
  function click(id) {
    var e = document.getElementById(id);
    if (!e) throw "no #" + id + " on this page";
    if (e.disabled || e.getAttribute("data-disabled") === "true") throw "#" + id + " is disabled right now";
    e.click();
    return { clicked: id };
  }
  function focusPrompt() {
    var e = document.getElementById("ai-prompt");
    if (!e) throw "no prompt box";
    e.focus();
    var n = (e.value || "").length;
    try { e.setSelectionRange(n, n); } catch (x) { /* not a text input */ }
    return { focused: "ai-prompt" };
  }

  function register() {
    if (!window.DeckBridge) return setTimeout(register, 50);
    window.DeckBridge.actions(PATH, {
      generate: function () { return click("ai-generate-btn"); },
      stop: function () { return click("ai-stop-btn"); },
      clear: function () { return click("ai-clear-btn"); },
      save: function () { return click("ai-save-btn"); },
      replay: function () { return click("ai-timeline-play"); },
      end: function () {
        var p = window.DeckBridge.pages[location.pathname];
        var f = p && p.fields.timeline;
        if (!f || !f.max) throw "no scene on the timeline";
        return window.DeckBridge.set("timeline", f.max);
      },
      focus_prompt: focusPrompt,
      set_prompt: function (a) {
        sp("ai-prompt", { value: a.text || "" });
        if (a.focus !== false) setTimeout(focusPrompt, 80);
        return {};
      },
      append_prompt: function (a) {
        var e = document.getElementById("ai-prompt");
        var cur = (e && e.value) || "";
        sp("ai-prompt", { value: (cur ? cur + (a.sep || "\n") : "") + (a.text || "") });
        setTimeout(focusPrompt, 80);
        return {};
      },
      preset: function (a) {
        var t = 0;
        if (a.provider) { sp("ai-provider", { value: a.provider }); t += 900; }
        if (a.model) {
          setTimeout(function () { sp("ai-model", { value: a.model }); }, t);
          t += 900;
        }
        setTimeout(function () {
          if (a.effort) sp("ai-effort", { value: a.effort });
          if (a.max_tokens) sp("ai-max-tokens", { value: a.max_tokens });
        }, t);
        var text = a.prompt || "";
        if (a.style) text += (text ? "\n\n" : "") + "Style: " + a.style;
        sp("ai-prompt", { value: text });
        if (a.focus !== false) setTimeout(focusPrompt, 80);
        return { preset: a.name || "", settle_ms: t };
      }
    });
  }
  register();
})();
