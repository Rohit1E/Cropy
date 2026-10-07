/* CROPY: clock, greeting, form validation. */
(function () {
  "use strict";

  var MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function tickClock() {
    var d = new Date();
    var dateEl = document.getElementById("clock-date");
    var timeEl = document.getElementById("clock-time");
    if (dateEl) dateEl.textContent = pad(d.getDate()) + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
    if (timeEl) {
      var h = d.getHours(), ap = h >= 12 ? "PM" : "AM";
      h = h % 12 || 12;
      timeEl.textContent = pad(h) + ":" + pad(d.getMinutes()) + " " + ap;
    }
  }

  function greeting() {
    var el = document.getElementById("greeting");
    if (!el) return;
    var h = new Date().getHours();
    el.textContent = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  }

  function validateField(input) {
    var wrap = input.closest(".field");
    var err = wrap && wrap.querySelector("[data-error-for]");
    var msg = "";
    var v = input.value.trim();
    if (input.tagName === "SELECT") {
      if (!v) msg = input.dataset.msg || "Please choose an option.";
    } else {
      var n = Number(v);
      var min = input.dataset.min !== undefined ? Number(input.dataset.min) : -Infinity;
      var max = input.dataset.max !== undefined ? Number(input.dataset.max) : Infinity;
      if (v === "" || !isFinite(n) || n < min || n > max) msg = input.dataset.msg || "Please enter a valid value.";
    }
    if (err) err.textContent = msg;
    if (wrap) wrap.classList.toggle("has-error", !!msg);
    return !msg;
  }

  function initRecommendForm() {
    var form = document.getElementById("recommend-form");
    if (!form) return;
    var fields = form.querySelectorAll("input[name], select[name]");
    fields.forEach(function (f) {
      f.addEventListener("blur", function () { validateField(f); });
      f.addEventListener("input", function () { if (f.closest(".has-error")) validateField(f); });
    });
    form.addEventListener("submit", function (e) {
      var ok = true;
      fields.forEach(function (f) { if (!validateField(f)) ok = false; });
      if (!ok) {
        e.preventDefault();
        var bad = form.querySelector(".has-error input, .has-error select");
        if (bad) bad.focus();
        return;
      }
      var btn = document.getElementById("recommend-submit");
      var status = document.getElementById("recommend-status");
      if (btn) { btn.disabled = true; btn.textContent = "Analyzing conditions..."; }
      if (status) status.textContent = "Analyzing conditions...";
    });
  }

  tickClock();
  setInterval(tickClock, 15000);
  greeting();
  initRecommendForm();
})();
