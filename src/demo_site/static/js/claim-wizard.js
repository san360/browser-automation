/* Contoso Insurance claim wizard (production version).
 * Client-side validation mirrors the server-side rules in app.py:validate_claim.
 */
(function () {
  "use strict";

  var form = document.getElementById("claim-form");
  if (!form) { return; }

  var options = JSON.parse(document.getElementById("claim-options").textContent);
  var steps = Array.prototype.slice.call(form.querySelectorAll("fieldset[data-step]"));
  var indicators = Array.prototype.slice.call(document.querySelectorAll("[data-step-indicator]"));
  var current = 0;

  function byId(id) { return document.getElementById(id); }

  function value(name) {
    var el = form.elements[name];
    if (!el) { return ""; }
    if (typeof RadioNodeList !== "undefined" && el instanceof RadioNodeList) { return el.value || ""; }
    if (el.type === "checkbox") { return el.checked ? "on" : ""; }
    return (el.value || "").trim();
  }

  function setError(name, message) {
    var holder = byId(name + "-error");
    if (holder) { holder.textContent = message || ""; }
    var input = byId(name);
    if (input && input.setAttribute) {
      if (message) {
        input.setAttribute("aria-invalid", "true");
        input.setAttribute("aria-describedby", name + "-error");
      } else {
        input.removeAttribute("aria-invalid");
      }
    }
    return !message;
  }

  function focusFirstError() {
    var invalid = steps[current].querySelector("[aria-invalid='true']");
    if (invalid && invalid.focus) { invalid.focus(); }
  }

  function parseAmount(raw) {
    var cleaned = String(raw).replace(/[$,\s]/g, "");
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) { return NaN; }
    return parseFloat(cleaned);
  }

  function phoneDigits(raw) { return (raw.match(/\d/g) || []).length; }

  function ageFrom(isoDate) {
    var d = new Date(isoDate + "T00:00:00");
    if (isNaN(d.getTime())) { return NaN; }
    var now = new Date();
    var age = now.getFullYear() - d.getFullYear();
    var m = now.getMonth() - d.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < d.getDate())) { age -= 1; }
    return age;
  }

  function todayIso() {
    var now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 10);
  }

  var validators = {
    1: function () {
      var ok = true;
      ok = setError("first_name", value("first_name").length >= 2 ? "" : "Enter your first name.") && ok;
      ok = setError("last_name", value("last_name").length >= 2 ? "" : "Enter your last name.") && ok;
      ok = setError("email", /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value("email")) ? "" : "Enter a valid email address, like name@example.com.") && ok;
      var digits = phoneDigits(value("phone"));
      ok = setError("phone", digits >= 10 && digits <= 15 ? "" : "Enter a valid phone number with 10 to 15 digits.") && ok;
      var age = ageFrom(value("dob"));
      ok = setError("dob", age >= 18 && age <= 120 ? "" : "The policyholder must be at least 18 years old.") && ok;
      ok = setError("contact_method", value("contact_method") ? "" : "Choose how we should contact you.") && ok;
      return ok;
    },
    2: function () {
      var ok = true;
      ok = setError("policy_number", /^CI-\d{6}$/i.test(value("policy_number")) ? "" : "Policy number must look like CI-123456.") && ok;
      ok = setError("policy_type", value("policy_type") ? "" : "Choose a policy type.") && ok;
      ok = setError("coverage_level", value("coverage_level") ? "" : "Choose a coverage level.") && ok;
      return ok;
    },
    3: function () {
      var ok = true;
      var incident = value("incident_date");
      var incidentError = "";
      if (!incident) { incidentError = "Enter the date of the incident."; }
      else if (incident > todayIso()) { incidentError = "The incident date cannot be in the future."; }
      ok = setError("incident_date", incidentError) && ok;
      ok = setError("claim_category", value("claim_category") ? "" : "Choose what happened.") && ok;
      var amount = parseAmount(value("estimated_amount"));
      ok = setError("estimated_amount", amount > 0 && amount <= 1000000 ? "" : "Enter an amount between 1 and 1,000,000, for example 1,250.00.") && ok;
      ok = setError("description", value("description").length >= 30 ? "" : "Describe what happened in at least 30 characters.") && ok;
      var report = value("police_report");
      ok = setError("police_report", report ? "" : "Tell us whether a police report was filed.") && ok;
      if (report === "yes") {
        ok = setError("police_report_number", /^PR-\d{4,8}$/i.test(value("police_report_number")) ? "" : "Police report number must look like PR-1234.") && ok;
      }
      if (value("witnesses")) {
        var count = parseInt(value("witness_count"), 10);
        ok = setError("witness_count", count >= 1 && count <= 10 ? "" : "Enter a number of witnesses between 1 and 10.") && ok;
      }
      return ok;
    },
    4: function () {
      return setError("consent", value("consent") ? "" : "You must confirm the declaration to submit.");
    }
  };

  function fillSelect(select, values, placeholder) {
    select.innerHTML = "";
    var first = document.createElement("option");
    first.value = "";
    first.textContent = placeholder;
    select.appendChild(first);
    values.forEach(function (v) {
      var option = document.createElement("option");
      option.value = v;
      option.textContent = v;
      select.appendChild(option);
    });
    select.disabled = values.length === 0;
  }

  function buildSummary() {
    var amount = parseAmount(value("estimated_amount"));
    var rows = [
      ["Policyholder", value("first_name") + " " + value("last_name")],
      ["Email", value("email")],
      ["Phone", value("phone")],
      ["Date of birth", value("dob")],
      ["Contact method", value("contact_method")],
      ["Policy number", value("policy_number").toUpperCase()],
      ["Policy type", value("policy_type")],
      ["Coverage level", value("coverage_level")],
      ["Incident date", value("incident_date")],
      ["What happened", value("claim_category")],
      ["Estimated amount", "$" + amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })],
      ["Police report", value("police_report") === "yes" ? value("police_report_number").toUpperCase() : "No"],
      ["Witnesses", value("witnesses") ? value("witness_count") : "None"],
      ["Photos available", value("photos_available") ? "Yes" : "No"],
      ["Description", value("description")]
    ];
    var dl = byId("review-summary");
    dl.innerHTML = "";
    rows.forEach(function (row) {
      var dt = document.createElement("dt");
      dt.textContent = row[0];
      var dd = document.createElement("dd");
      dd.textContent = row[1];
      dl.appendChild(dt);
      dl.appendChild(dd);
    });
  }

  function showStep(index) {
    current = index;
    steps.forEach(function (step, i) { step.hidden = i !== index; });
    indicators.forEach(function (li, i) {
      li.classList.toggle("active", i === index);
      li.classList.toggle("done", i < index);
      if (i === index) { li.setAttribute("aria-current", "step"); } else { li.removeAttribute("aria-current"); }
    });
    if (index === steps.length - 1) { buildSummary(); }
    var legend = steps[index].querySelector("legend");
    if (legend) { legend.setAttribute("tabindex", "-1"); legend.focus(); }
    window.scrollTo(0, 0);
  }

  byId("policy_type").addEventListener("change", function () {
    var type = this.value;
    fillSelect(byId("coverage_level"), options.coverage[type] || [], type ? "Choose a coverage level" : "Choose a policy type first");
    fillSelect(byId("claim_category"), options.categories[type] || [], "Choose a category");
  });

  Array.prototype.forEach.call(form.querySelectorAll("input[name='police_report']"), function (radio) {
    radio.addEventListener("change", function () {
      var show = value("police_report") === "yes";
      byId("police-report-number-group").hidden = !show;
      if (!show) { byId("police_report_number").value = ""; setError("police_report_number", ""); }
    });
  });

  byId("witnesses").addEventListener("change", function () {
    byId("witness-count-group").hidden = !this.checked;
    if (!this.checked) { byId("witness_count").value = ""; setError("witness_count", ""); }
  });

  form.addEventListener("click", function (event) {
    var target = event.target;
    if (target.matches("[data-next]")) {
      if (validators[current + 1]()) { showStep(current + 1); } else { focusFirstError(); }
    } else if (target.matches("[data-back]")) {
      showStep(Math.max(0, current - 1));
    }
  });

  form.addEventListener("submit", function (event) {
    if (!validators[4]()) { event.preventDefault(); focusFirstError(); }
  });
})();
