(function () {
  "use strict";
  var body = document.body;
  var lat = parseFloat(body.dataset.defaultLat) || 30.3165;
  var lon = parseFloat(body.dataset.defaultLon) || 78.0322;
  var name = body.dataset.defaultName || "Dehradun";
  var humidityInput = document.querySelector('input[name="humidity"]');
  var rainfallInput = document.querySelector('input[name="rainfall"]');
  var seasonInput = document.querySelector('select[name="season"]');
  var panel = document.querySelector('[data-recommend-weather]');
  if (!panel) return;

  var status = panel.querySelector('[data-rw-status]');
  var source = panel.querySelector('[data-rw-source]');
  var city = panel.querySelector('[data-rw-city]');
  var temp = panel.querySelector('[data-rw-temp]');
  var humidity = panel.querySelector('[data-rw-humidity]');
  var rain = panel.querySelector('[data-rw-rain]');
  var condition = panel.querySelector('[data-rw-condition]');
  var useBtn = panel.querySelector('[data-use-weather]');
  var refreshBtn = panel.querySelector('[data-refresh-recommend-weather]');

  function val(v, suffix) { return v === null || v === undefined ? "—" : v + (suffix || ""); }
  function seasonForMonth(m) {
    if (m >= 6 && m <= 9) return "Kharif";
    if (m === 10 || m <= 2) return "Rabi";
    return "Zaid";
  }
  function setStatus(text, cls) {
    status.textContent = text || "";
    status.className = cls || "weather-use-note";
  }
  function applyWeather(data) {
    var c = data.current || {};
    var days = data.daily || [];
    var forecastRain = days.slice(0, 7).reduce(function (sum, d) {
      return sum + (Number(d.precipitation_mm) || 0);
    }, 0);

    city.textContent = name;
    temp.textContent = val(c.temperature, "°C");
    humidity.textContent = val(c.humidity, "%");
    rain.textContent = forecastRain ? forecastRain.toFixed(1) + " mm" : "0 mm";
    condition.textContent = c.condition || "Current conditions";
    source.textContent = data.source || "Weather API";

    if (humidityInput && c.humidity !== null && c.humidity !== undefined) {
      humidityInput.value = Math.round(Number(c.humidity));
      humidityInput.closest('.field').classList.add('field--weather-filled');
    }
    if (rainfallInput && forecastRain > 0) {
      rainfallInput.value = Math.round(forecastRain);
      rainfallInput.closest('.field').classList.add('field--weather-filled');
    }
    if (seasonInput) seasonInput.value = seasonForMonth(new Date().getMonth() + 1);
    setStatus("Live weather values loaded into the recommendation form.");
  }

  function load(refresh) {
    setStatus("Loading live weather…");
    if (refreshBtn) refreshBtn.disabled = true;
    var url = "/api/weather?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon) + (refresh ? "&refresh=1" : "");
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok || !d.available) throw new Error(d.error || "Weather unavailable"); return d; }); })
      .then(applyWeather)
      .catch(function (e) { setStatus(e.message, "weather-error"); })
      .finally(function () { if (refreshBtn) refreshBtn.disabled = false; });
  }

  if (useBtn) useBtn.addEventListener("click", function () { load(false); });
  if (refreshBtn) refreshBtn.addEventListener("click", function () { load(true); });
  load(false);
}());
