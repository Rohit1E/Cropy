/* CROPY weather UI. Talks only to /api/weather (the Google key stays on the server). */
(function () {
  "use strict";

  var STORE_KEY = "cropy_location_v2";
  var body = document.body;
  var DEFAULT = {
    name: body.dataset.defaultName || "Dehradun",
    lat: parseFloat(body.dataset.defaultLat) || 30.3165,
    lon: parseFloat(body.dataset.defaultLon) || 78.0322
  };

  // ---------- helpers ----------
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") n.className = attrs[k];
      else if (k === "text") n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }
  function show(v, suffix) { return v === null || v === undefined ? "n/a" : v + (suffix || ""); }
  function safeUrl(u) { return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null; }
  function wxIcon(src, alt, cls) {
    if (!src) return null;
    if (typeof src === "string" && src.indexOf("emoji:") === 0) {
      return el("span", { class: (cls || "wx-icon") + " wx-emoji", role: "img", "aria-label": alt || "Weather" , text: src.slice(6) });
    }
    var img = el("img", { src: src, alt: alt || "", class: cls || "", loading: "lazy", width: "40", height: "40" });
    img.addEventListener("error", function () { img.remove(); });
    return img;
  }
  function fmtTime(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  // ---------- location ----------
  function getLocation() {
    try {
      var s = JSON.parse(localStorage.getItem(STORE_KEY));
      if (s && isFinite(s.lat) && isFinite(s.lon)) return s;
    } catch (e) { /* storage unavailable */ }
    return DEFAULT;
  }
  function saveLocation(loc) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(loc)); } catch (e) { /* ignore */ }
  }
  function paintLocationName() {
    var n = document.getElementById("loc-name");
    if (n) n.textContent = getLocation().name;
  }

  // ---------- rendering ----------
  function renderUnavailable(box, message, retry) {
    clear(box);
    var wrap = el("div", { class: "wx-unavail", role: "status" }, [
      el("b", { text: "Weather unavailable" }),
      el("p", { class: "muted", text: "Weather data is temporarily unavailable. Your crop recommendation and farm plan are still available." }),
      message ? el("p", { class: "helper", text: message }) : null
    ]);
    box.appendChild(wrap);
  }

  function renderCurrent(box, c) {
    clear(box);
    var compact = box.dataset.compact === "1";
    var main = el("div", { class: "wx-main" }, [
      wxIcon(c.icon, c.condition, "wx-icon"),
      el("div", {}, [
        el("div", { class: "wx-temp", text: show(c.temperature, "°C") }),
        el("div", { class: "wx-cond", text: c.condition || "" })
      ])
    ]);
    var rows = [
      ["Feels like", show(c.feels_like, "°C")],
      ["Humidity", show(c.humidity, "%")],
      ["Rain probability", show(c.rain_probability, "%")],
      ["Wind", c.wind_kmh === null || c.wind_kmh === undefined ? "n/a" : c.wind_kmh + " km/h" + (c.wind_direction ? " " + c.wind_direction : "")]
    ];
    if (!compact) {
      rows.splice(3, 0, ["Precipitation", show(c.precipitation_mm, " mm")]);
      rows.push(["Cloud cover", show(c.cloud_cover, "%")]);
      rows.push(["UV index", show(c.uv_index)]);
    }
    var grid = el("dl", { class: "wx-grid" });
    rows.forEach(function (r) { grid.appendChild(el("div", {}, [el("dt", { text: r[0] }), el("dd", { text: r[1] })])); });
    box.appendChild(main);
    box.appendChild(grid);
  }

  function renderDaily(box, days) {
    clear(box);
    if (!days || !days.length) { box.appendChild(el("p", { class: "muted", text: "Forecast unavailable." })); return; }
    var row = el("div", { class: "forecast", role: "list" });
    var todayIso = new Date().toISOString().slice(0, 10);
    days.forEach(function (d, i) {
      var label = i === 0 ? "TODAY" : "";
      if (!label && d.date) {
        var dt = new Date(d.date + "T12:00:00");
        label = dt.toLocaleDateString(undefined, { weekday: "short" }).toUpperCase();
      }
      var card = el("div", { class: "fc-day" + (i === 0 ? " is-today" : ""), role: "listitem" }, [
        el("div", { class: "fc-day__label", text: label || "DAY " + (i + 1) }),
        wxIcon(d.icon, d.condition),
        el("div", { class: "fc-day__max", text: show(d.max_temp === null ? null : Math.round(d.max_temp), "°") }),
        el("div", { class: "fc-day__min", text: show(d.min_temp === null ? null : Math.round(d.min_temp), "°") }),
        el("div", { class: "fc-day__rain", text: d.rain_probability === null || d.rain_probability === undefined ? "" : d.rain_probability + "% rain" }),
        el("div", { class: "fc-day__cond", text: d.condition || "" })
      ]);
      row.appendChild(card);
    });
    box.appendChild(row);
  }

  function renderHourly(box, hours) {
    clear(box);
    if (!hours || !hours.length) { box.appendChild(el("p", { class: "muted", text: "Hourly forecast unavailable." })); return; }
    var row = el("div", { class: "hourly" });
    hours.forEach(function (h) {
      var t = h.time ? new Date(h.time) : null;
      var label = t && !isNaN(t) ? t.toLocaleTimeString(undefined, { hour: "numeric" }) : (h.hour !== null && h.hour !== undefined ? h.hour + ":00" : "");
      row.appendChild(el("div", { class: "hr" }, [
        el("small", { text: label }),
        wxIcon(h.icon, h.condition),
        el("b", { text: show(h.temperature === null ? null : Math.round(h.temperature), "°") }),
        el("span", { class: "rain", text: h.rain_probability === null || h.rain_probability === undefined ? "" : h.rain_probability + "%" })
      ]));
    });
    box.appendChild(row);
  }

  function alertNode(a) {
    var ic = a.level === "info" ? "i-info" : "i-alert";
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#" + ic);
    svg.appendChild(use);
    return el("div", { class: "alert alert--" + a.level, role: "note" }, [
      svg,
      el("div", { class: "alert__body" }, [
        el("div", { class: "alert__title", text: a.title }),
        el("p", { text: a.message }),
        el("span", { class: "alert__src", text: a.source || "CROPY Weather Advisory" })
      ])
    ]);
  }

  function officialNode(a) {
    var meta = [];
    if (a.severity) meta.push("Severity: " + String(a.severity).toLowerCase());
    if (a.event_type) meta.push(String(a.event_type).replace(/_/g, " ").toLowerCase());
    if (a.start) meta.push("From " + fmtTime(a.start));
    if (a.end) meta.push("until " + fmtTime(a.end));
    if (a.area) meta.push(a.area);
    var kids = [
      el("div", { class: "official__tag", text: "Official weather alert" }),
      el("h3", { text: a.title }),
      el("div", { class: "official__meta", text: meta.join(" · ") })
    ];
    if (a.description) kids.push(el("p", { text: a.description }));
    if (a.instructions && a.instructions.length) {
      var ul = el("ul");
      a.instructions.forEach(function (i) { ul.appendChild(el("li", { text: i })); });
      kids.push(ul);
    }
    var src = [];
    if (a.source) src.push("Source: " + a.source);
    var srcEl = el("div", { class: "official__src", text: src.join("") });
    var url = safeUrl(a.source_url);
    if (url) {
      srcEl.appendChild(document.createTextNode(src.length ? " " : ""));
      srcEl.appendChild(el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: "Authority page" }));
    }
    if (src.length || url) kids.push(srcEl);
    return el("div", { class: "official official--" + (a.level === "high" ? "high" : "warning") }, kids);
  }

  function renderAlerts(data) {
    var dyn = document.querySelector("[data-weather-alerts]");
    var official = document.querySelector("[data-weather-alerts-official]");
    var emptyMsg = document.querySelector("[data-alerts-empty]");
    var list = document.querySelector("[data-alert-list]");
    var staticCount = list ? list.querySelectorAll(":scope > .alert").length : 0;
    var added = 0;
    if (official) {
      clear(official);
      (data.alerts || []).forEach(function (a) { official.appendChild(officialNode(a)); added++; });
    }
    if (dyn) {
      clear(dyn);
      (data.advisories || []).forEach(function (a) { dyn.appendChild(alertNode(a)); added++; });
    }
    if (emptyMsg) emptyMsg.hidden = (added + staticCount) > 0;
  }

  function renderConsiderations(box, data) {
    clear(box);
    var adv = data.advisories || [];
    if (!adv.length) {
      box.appendChild(el("p", { class: "muted", text: data.available ? "No weather considerations right now." : "Weather unavailable. Considerations will appear when it loads." }));
      return;
    }
    adv.forEach(function (a) { box.appendChild(alertNode(a)); });
  }

  // ---------- loading ----------
  var inflight = false;
  function boxes() {
    return {
      current: document.querySelectorAll("[data-weather-current]"),
      daily: document.querySelectorAll("[data-weather-forecast]"),
      hourly: document.querySelectorAll("[data-weather-hourly]"),
      cons: document.querySelectorAll("[data-weather-considerations]"),
      status: document.querySelectorAll("[data-weather-status]")
    };
  }
  function setLoading(b, on) {
    b.status.forEach(function (s) { s.textContent = on ? "Updating weather..." : s.textContent; });
    document.querySelectorAll("[data-refresh-weather]").forEach(function (x) { x.disabled = on; });
  }

  function loadWeather(refresh) {
    var b = boxes();
    var any = b.current.length || b.daily.length || b.hourly.length || b.cons.length ||
      document.querySelector("[data-weather-alerts]");
    if (!any || inflight) return;
    inflight = true;
    setLoading(b, true);
    var loc = getLocation();
    var url = "/api/weather?lat=" + encodeURIComponent(loc.lat) + "&lon=" + encodeURIComponent(loc.lon) + (refresh ? "&refresh=1" : "");
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, 20000);
    fetch(url, { signal: ctl.signal, headers: { "Accept": "application/json" } })
      .then(async function (r) {
        var text = await r.text();
        var data;
        try { data = JSON.parse(text); }
        catch (e) { data = { available: false, error: "Server returned HTTP " + r.status + " instead of JSON. Check the Flask terminal." }; }
        if (!r.ok && !data.error) data.error = "Weather request failed (HTTP " + r.status + ").";
        return data;
      })
      .catch(function () { return { available: false, error: "Could not reach the CROPY server." }; })
      .then(function (data) {
        clearTimeout(timer);
        data.advisories = data.advisories || [];
        data.alerts = data.alerts || [];
        if (data.available && data.current) b.current.forEach(function (n) { renderCurrent(n, data.current); });
        else b.current.forEach(function (n) { renderUnavailable(n, data.error); });
        b.daily.forEach(function (n) { data.available && data.daily && data.daily.length ? renderDaily(n, data.daily) : renderUnavailable(n, data.available ? "Daily forecast unavailable." : data.error); });
        b.hourly.forEach(function (n) { if (data.available) renderHourly(n, data.hourly); else clear(n); });
        b.cons.forEach(function (n) { renderConsiderations(n, data); });
        renderAlerts(data);
        var msg = "";
        if (data.available) {
          msg = "Weather for " + loc.name + ". ";
          if (data.source) msg += data.source + " · ";
          if (data.fetched_at) msg += "Updated " + new Date(data.fetched_at * 1000).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) + ". ";
          if (data.stale) msg += "Showing the last available data because the latest refresh failed. ";
          else if (data.error) msg += "Some weather data could not be loaded. ";
          if (data.alerts_available === false) msg += "Official alerts could not be checked.";
        }
        b.status.forEach(function (s) { s.textContent = msg; });
      })
      .then(function () { inflight = false; setLoading(b, false); });
  }

  // ---------- location dialog ----------
  function initDialog() {
    var dlg = document.getElementById("loc-dialog");
    var open = document.getElementById("loc-open");
    if (!dlg || !open) return;
    var city = document.getElementById("loc-city");
    var lat = document.getElementById("loc-lat");
    var lon = document.getElementById("loc-lon");
    var err = document.getElementById("loc-error");
    var geoMsg = document.getElementById("loc-geo-msg");

    function showErr(m) { err.textContent = m; err.hidden = !m; }
    function apply(loc) {
      saveLocation(loc);
      paintLocationName();
      dlg.close();
      loadWeather(true);
    }

    open.addEventListener("click", function () {
      var cur = getLocation();
      lat.value = cur.lat; lon.value = cur.lon;
      showErr(""); geoMsg.textContent = "";
      if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    });
    document.getElementById("loc-cancel").addEventListener("click", function () { dlg.close(); });
    city.addEventListener("change", function () {
      var parts = city.value.split(",");
      lat.value = parts[0]; lon.value = parts[1];
    });
    document.getElementById("loc-geo").addEventListener("click", function () {
      if (!navigator.geolocation) { geoMsg.textContent = "Location is not supported by this browser. Choose a city or enter coordinates."; return; }
      geoMsg.textContent = "Waiting for permission...";
      navigator.geolocation.getCurrentPosition(function (pos) {
        apply({ name: "My location", lat: +pos.coords.latitude.toFixed(3), lon: +pos.coords.longitude.toFixed(3) });
      }, function (e) {
        geoMsg.textContent = e && e.code === 1
          ? "Location permission was denied. Choose a city or enter coordinates instead."
          : "Could not determine your location. Choose a city or enter coordinates instead.";
      }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
    });
    document.getElementById("loc-apply").addEventListener("click", function () {
      var la = parseFloat(lat.value), lo = parseFloat(lon.value);
      if (!isFinite(la) || !isFinite(lo) || la < -90 || la > 90 || lo < -180 || lo > 180) {
        showErr("Enter a latitude between -90 and 90 and a longitude between -180 and 180."); return;
      }
      var opt = city.options[city.selectedIndex];
      var matched = opt && opt.value === la + "," + lo;
      apply({ name: matched ? opt.dataset.name : la.toFixed(2) + ", " + lo.toFixed(2), lat: la, lon: lo });
    });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-refresh-weather]");
    if (btn) loadWeather(true);
  });

  paintLocationName();
  initDialog();
  loadWeather(false);
})();
