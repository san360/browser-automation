/* Contoso Insurance claim wizard - beta build (new claims experience). */
(function () {
  "use strict";

  var form = document.getElementById("claim-form");
  if (!form) { return; }

  var options = JSON.parse(document.getElementById("claim-options").textContent);
  var steps = Array.prototype.slice.call(form.querySelectorAll("fieldset[data-step]"));
  var indicators = Array.prototype.slice.call(document.querySelectorAll("[data-step-indicator]"));
  var current = 0;
  var incidentStepReady = false;

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
      if (message) { input.setAttribute("aria-invalid", "true"); } else { input.removeAttribute("aria-invalid"); }
    }
    return !message;
  }

  /* Cookie consent dialog. */
  var banner = byId("cookie-banner");
  var acceptButton = byId("cookie-accept");
  var closeButton = document.querySelector(".cookie-banner .close-button");
  function hideBanner() { if (banner) { banner.hidden = true; } }
  if (acceptButton) { acceptButton.addEventListener("click", hideBanner); }
  if (closeButton) { closeButton.addEventListener("click", hideBanner); }

  var validators = {
    1: function () {
      var ok = true;
      ok = setError("first_name", value("first_name").length >= 2 ? "" : "Enter your first name.") && ok;
      ok = setError("last_name", value("last_name").length >= 2 ? "" : "Enter your last name.") && ok;
      ok = setError("email", /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value("email")) ? "" : "Enter a valid email address.") && ok;
      ok = setError("phone", /^\d{10}$/.test(value("phone")) ? "" : "Enter a valid phone number.") && ok;
      ok = setError("dob", value("dob") ? "" : "Enter your date of birth.") && ok;
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
      ok = setError("incident_date", value("incident_date") ? "" : "Enter the date of the incident.") && ok;
      ok = setError("claim_category", value("claim_category") ? "" : "Choose what happened.") && ok;
      ok = setError("estimated_amount", isNaN(parseFloat(value("estimated_amount"))) ? "Enter an amount." : "") && ok;
      ok = setError("description", value("description").length >= 30 ? "" : "Describe what happened in at least 30 characters.") && ok;
      var report = value("police_report");
      ok = setError("police_report", report ? "" : "Tell us whether a police report was filed.") && ok;
      if (report === "yes") {
        ok = setError("police_report_number", /^PR-\d{4,8}$/i.test(value("police_report_number")) ? "" : "Police report number must look like PR-1234.") && ok;
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
    var amount = parseInt(value("estimated_amount"), 10);
    var rows = [
      ["Policyholder", value("first_name") + " " + value("last_name")],
      ["Email", value("email")],
      ["Phone", value("phone")],
      ["Policy number", value("policy_number").toUpperCase()],
      ["Policy type", value("policy_type")],
      ["Coverage level", value("coverage_level")],
      ["Incident date", value("incident_date")],
      ["What happened", value("claim_category")],
      ["Estimated amount", "$" + amount.toFixed(2)],
      ["Police report", value("police_report") === "yes" ? value("police_report_number").toUpperCase() : "No"],
      ["Witnesses", value("witnesses") ? value("witness_count") || "(not provided)" : "None"],
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

  function initIncidentStep() {
    incidentStepReady = true;
    byId("witness-count").addEventListener("input", function () { setError("witness_count", ""); });
    byId("witnesses").addEventListener("change", function () {
      byId("witness-count-group").hidden = !this.checked;
    });
  }

  function showStep(index) {
    current = index;
    steps.forEach(function (step, i) { step.hidden = i !== index; });
    indicators.forEach(function (li, i) {
      li.classList.toggle("active", i === index);
      li.classList.toggle("done", i < index);
    });
    if (index === steps.length - 1) { buildSummary(); }
    window.scrollTo(0, 0);
    if (index === 2 && !incidentStepReady) { initIncidentStep(); }
  }

  byId("policy_type").addEventListener("change", function () {
    var type = this.value;
    var coverageKey = type === "travel" ? "Travel" : type;
    fillSelect(byId("coverage_level"), options.coverage[coverageKey] || [], "Choose a coverage level");
    fillSelect(byId("claim_category"), options.categories[type] || [], "Choose a category");
  });

  Array.prototype.forEach.call(form.querySelectorAll("input[name='police_report']"), function (radio) {
    radio.addEventListener("change", function () {
      byId("police-report-number-group").hidden = value("police_report") !== "yes";
    });
  });

  form.addEventListener("click", function (event) {
    var target = event.target;
    if (target.matches("[data-next]")) {
      if (validators[current + 1]()) { showStep(current + 1); }
    } else if (target.matches("[data-back]")) {
      showStep(current === 2 ? 0 : Math.max(0, current - 1));
    } else if (target.id === "submit-claim") {
      if (validators[4]()) { form.submit(); }
    }
  });
})();
