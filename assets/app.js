/* Agentic Systems, Hands-on - site behavior. Plain ES2017, works from file:// with no server. */
(function () {
  "use strict";
  var body = document.body;
  var root = body.getAttribute("data-root") || "";
  var slug = body.getAttribute("data-page") || "";
  var INDEX = window.TUTORIAL_INDEX || [];

  function lsGet(key, fallback) {
    try { var v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }
  function lsSet(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage disabled */ } }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function $all(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }

  /* ---- theme ---- */
  var themeBtn = document.querySelector(".theme-btn");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("ast-theme", next); } catch (e) { /* ignore */ }
  });

  /* ---- mobile navigation ---- */
  var menuBtn = document.querySelector(".menu-btn");
  if (menuBtn) menuBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = body.classList.toggle("nav-open");
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("click", function (e) {
    if (body.classList.contains("nav-open") && !e.target.closest(".sidebar") && !e.target.closest(".menu-btn")) body.classList.remove("nav-open");
  });
  var current = document.querySelector(".sidebar a.current");
  var sidebarEl = document.querySelector(".sidebar");
  if (current && sidebarEl) {
    // scroll only the sidebar (scrollIntoView would also move the page away from a #section target)
    var r = current.getBoundingClientRect(), s = sidebarEl.getBoundingClientRect();
    sidebarEl.scrollTop += (r.top - s.top) - sidebarEl.clientHeight / 2;
  }

  /* ---- progress ---- */
  var chapterSlugs = INDEX.filter(function (p) { return /^Chapter /.test(p.l); })
    .map(function (p) { return p.u.replace(/^chapters\//, "").replace(/\.html$/, ""); });
  function progress() { return lsGet("ast-progress", {}); }
  function renderProgress() {
    var done = progress();
    var n = chapterSlugs.filter(function (s) { return done[s]; }).length;
    var pct = chapterSlugs.length ? Math.round((100 * n) / chapterSlugs.length) : 0;
    $all(".progress-mini .fill").forEach(function (el) { el.style.width = pct + "%"; });
    $all(".progress-mini .pct").forEach(function (el) { el.textContent = pct + "%"; });
    $all("a[data-slug]").forEach(function (a) { a.classList.toggle("is-done", !!done[a.getAttribute("data-slug")]); });
    $all(".complete-btn").forEach(function (b) { b.classList.toggle("done", !!done[b.getAttribute("data-slug")]); });
    $all(".part-progress").forEach(function (el) {
      var block = el.closest(".part-block");
      var cards = block ? $all(".ch-card", block) : [];
      var countable = cards.filter(function (c) { return chapterSlugs.indexOf(c.getAttribute("data-slug")) >= 0; });
      if (!countable.length) { el.innerHTML = ""; return; }
      var d = countable.filter(function (c) { return done[c.getAttribute("data-slug")]; }).length;
      el.innerHTML = '<span class="bar"><span class="fill" style="width:' + Math.round((100 * d) / countable.length) + '%"></span></span><span>' +
        d + " / " + countable.length + " complete</span>";
    });
  }
  $all(".complete-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = progress(), s = b.getAttribute("data-slug");
      if (d[s]) delete d[s]; else d[s] = Date.now();
      lsSet("ast-progress", d);
      renderProgress();
    });
  });
  var isChapter = INDEX.some(function (p) { return p.u === "chapters/" + slug + ".html"; });
  if (isChapter) lsSet("ast-last", slug);
  var cont = document.querySelector(".btn.continue");
  var last = lsGet("ast-last", null);
  if (cont && last) {
    var entry = INDEX.filter(function (p) { return p.u === "chapters/" + last + ".html"; })[0];
    if (entry) { cont.href = "chapters/" + last + ".html"; cont.textContent = "Continue: " + entry.l + " \u00b7 " + entry.t; cont.hidden = false; }
  }
  renderProgress();

  /* ---- copy buttons ---- */
  $all(".code .copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var text = btn.closest(".code").querySelector("code").innerText.replace(/\n$/, "");
      function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1400); }
      function fallback() {
        var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (e) { /* ignore */ }
        ta.remove(); done();
      }
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
    });
  });

  /* ---- quizzes ---- */
  $all(".q").forEach(function (q) {
    var explain = q.querySelector(".q-explain");
    $all(".opt", q).forEach(function (opt) {
      opt.addEventListener("click", function () {
        if (q.classList.contains("answered")) return;
        q.classList.add("answered");
        var ok = opt.getAttribute("data-correct") === "true";
        opt.classList.add(ok ? "correct" : "wrong");
        if (!ok) { var right = q.querySelector('.opt[data-correct="true"]'); if (right) right.classList.add("correct"); }
        var verdict = document.createElement("strong");
        verdict.className = "verdict"; verdict.textContent = ok ? "Correct. " : "Not quite. ";
        explain.insertBefore(verdict, explain.firstChild);
        explain.hidden = false;
        var retry = document.createElement("button");
        retry.type = "button"; retry.className = "q-retry"; retry.textContent = "\u21bb Try again";
        retry.addEventListener("click", function () {
          q.classList.remove("answered");
          $all(".opt", q).forEach(function (o) { o.classList.remove("correct", "wrong"); });
          var v = explain.querySelector(".verdict"); if (v) v.remove();
          explain.hidden = true; retry.remove();
        });
        explain.parentNode.insertBefore(retry, explain.nextSibling);
      });
    });
  });

  /* ---- heading anchors + table-of-contents scrollspy ---- */
  $all(".chapter h2[id], .chapter h3[id]").forEach(function (h) {
    var a = document.createElement("a");
    a.className = "anchor"; a.href = "#" + h.id; a.textContent = "#"; a.setAttribute("aria-label", "Link to this section");
    h.appendChild(a);
  });
  var tocLinks = $all(".toc a");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[decodeURIComponent(a.getAttribute("href").slice(1))] = a; });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && byId[en.target.id]) {
          tocLinks.forEach(function (a) { a.classList.remove("active"); });
          byId[en.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -72% 0px" });
    $all(".chapter h2[id], .chapter h3[id]").forEach(function (h) { obs.observe(h); });
  }

  /* ---- search ---- */
  var input = document.getElementById("search");
  var box = document.getElementById("search-results");
  function terms(q) { return q.toLowerCase().split(/\s+/).filter(function (t) { return t.length > 1; }); }
  function search(q) {
    var ts = terms(q), out = [];
    if (!ts.length) return out;
    INDEX.forEach(function (p) {
      var title = (p.t + " " + p.l + " " + p.p).toLowerCase();
      p.h.forEach(function (sec) {
        var head = sec[1].toLowerCase(), text = sec[2].toLowerCase(), score = 0, all = true;
        ts.forEach(function (t) {
          var s = 0;
          if (title.indexOf(t) >= 0) s += 6;
          if (head.indexOf(t) >= 0) s += 5;
          var c = text.split(t).length - 1;
          s += Math.min(c, 6);
          if (!s) all = false;
          score += s;
        });
        if (all && score) out.push({ p: p, id: sec[0], h: sec[1], text: sec[2], score: score });
      });
    });
    out.sort(function (a, b) { return b.score - a.score; });
    return out.slice(0, 14);
  }
  function snippet(text, ts) {
    var low = text.toLowerCase(), at = -1;
    for (var i = 0; i < ts.length && at < 0; i++) at = low.indexOf(ts[i]);
    var start = Math.max(0, at - 70);
    var s = esc((start ? "\u2026" : "") + text.slice(start, start + 190) + "\u2026");
    ts.forEach(function (t) { s = s.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>"); });
    return s;
  }
  function showResults() {
    var q = input.value.trim();
    if (!q) { box.hidden = true; return; }
    var ts = terms(q), res = search(q);
    box.innerHTML = res.length ? res.map(function (r, i) {
      return '<a class="sr' + (i === 0 ? " sel" : "") + '" href="' + root + r.p.u + (r.id ? "#" + r.id : "") + '">' +
        '<span class="sr-t">' + esc(r.p.l) + " \u00b7 " + esc(r.p.t) + "</span>" +
        '<span class="sr-h">' + esc(r.h) + "</span>" +
        '<span class="sr-s">' + snippet(r.text, ts) + "</span></a>";
    }).join("") : '<div class="sr-empty">No results for \u201c' + esc(q) + "\u201d</div>";
    box.hidden = false;
  }
  if (input && box) {
    input.addEventListener("input", showResults);
    input.addEventListener("focus", function () { if (input.value.trim()) showResults(); });
    input.addEventListener("keydown", function (e) {
      var items = $all(".sr", box), i = -1;
      items.forEach(function (a, k) { if (a.classList.contains("sel")) i = k; });
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        if (i >= 0) items[i].classList.remove("sel");
        i = e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
        items[i].classList.add("sel"); items[i].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        var target = items[i >= 0 ? i : 0]; if (target) window.location.href = target.href;
      } else if (e.key === "Escape") { box.hidden = true; input.blur(); }
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".search")) box.hidden = true; });
  }

  /* ---- keyboard shortcuts ---- */
  document.addEventListener("keydown", function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    var typing = /INPUT|TEXTAREA|SELECT/.test(tag);
    if (e.key === "/" && !typing && input) { e.preventDefault(); input.focus(); input.select(); return; }
    if (typing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var link = null;
    if (e.key === "ArrowLeft") link = document.querySelector(".pager a.prev");
    if (e.key === "ArrowRight") link = document.querySelector(".pager a.next");
    if (link) window.location.href = link.href;
  });
})();
