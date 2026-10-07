/* CROPY task completion (persisted in SQLite via the API) and schedule filters. */
(function () {
  "use strict";

  function slug(s) { return String(s).toLowerCase().replace(/\s+/g, "-"); }

  function updateCounts(counts) {
    if (!counts) return;
    ["due", "overdue", "upcoming", "completed"].forEach(function (k) {
      document.querySelectorAll('[data-count="' + k + '"]').forEach(function (n) { n.textContent = counts[k]; });
    });
  }

  function paintRow(row, t) {
    row.dataset.status = t.status;
    row.className = row.className.replace(/task--[\w-]+/g, "").trim() + " task--" + slug(t.status);
    var chip = row.querySelector("[data-status-chip]");
    if (chip) { chip.textContent = t.status; chip.className = "chip chip--" + slug(t.status); }
    var due = row.querySelector("[data-due-text]");
    if (due) due.textContent = t.due_text;
    var btn = row.querySelector("[data-toggle-task]");
    if (btn) {
      btn.dataset.completed = t.completed ? "true" : "false";
      if (btn.closest(".mini-tasks")) return;
      btn.textContent = t.completed ? "Undo" : "✓ Mark Complete";
      btn.classList.toggle("btn--ghost", t.completed);
    }
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-toggle-task]");
    if (!btn || btn.disabled) return;
    var id = btn.dataset.toggleTask;
    var wantComplete = btn.dataset.completed !== "true";
    var row = btn.closest("[data-task-id]");
    btn.disabled = true;
    fetch("/api/tasks/" + encodeURIComponent(id) + "/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ completed: wantComplete })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Failed");
        if (row) {
          if (row.parentElement && row.parentElement.classList.contains("mini-tasks") && data.task.completed) row.remove();
          else paintRow(row, data.task);
        }
        updateCounts(data.counts);
        applyFilter();
      })
      .catch(function () { btn.textContent = "Could not save. Retry"; })
      .then(function () { btn.disabled = false; });
  });

  // ---------- filters ----------
  var current = "all";
  function matches(status) {
    if (current === "all") return true;
    if (current === "today") return status === "Due Today" || status === "Overdue";
    if (current === "upcoming") return status === "Upcoming";
    if (current === "completed") return status === "Completed";
    return true;
  }
  function applyFilter() {
    var list = document.getElementById("task-list");
    if (!list) return;
    var visible = 0;
    list.querySelectorAll(".task").forEach(function (li) {
      var ok = matches(li.dataset.status);
      li.hidden = !ok;
      if (ok) visible++;
    });
    var empty = document.getElementById("filter-empty");
    if (empty) empty.hidden = visible > 0;
  }
  document.querySelectorAll("[data-filter]").forEach(function (b) {
    b.addEventListener("click", function () {
      current = b.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach(function (x) { x.classList.toggle("is-active", x === b); });
      applyFilter();
    });
  });
})();
