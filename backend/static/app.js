"use strict";

/**
 * EquiTask AI — Phase 4 frontend (demo / research console).
 *
 * A single-page application that talks to the /api/v1 backend.
 * Design notes (honest about limitations):
 * - No external assets; system fonts only; inline SVG none.
 * - Bearer token held in memory + sessionStorage (demo only).
 * - Idempotency keys generated client-side for mutation endpoints.
 * - Where the backend has no endpoint for a flow (deliverables, approvals,
 *   organization/user listing), the UI simulates the action and says so
 *   explicitly. Nothing is claimed production-ready.
 */

const EquiTask = (() => {
  // -------------------------------------------------------------------------
  // Config
  // -------------------------------------------------------------------------
  const API_BASE = "/api/v1";
  const STORAGE_KEY = "equitask_token";
  const SUPPORTED_LANGS = ["en", "fr", "es"];

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  let state = {
    token: null,
    user: null,            // { id, email, role, display_name }
    lang: "en",
    locales: {},
    routerRoot: "#/",
    // Client-side caches for resources the backend cannot list back to us.
    volunteer: null,
    skills: [],
    availability: [],
    languages: [],
    preferences: {},
    proposals: [],
    orgs: [],              // simulated
    users: [],             // simulated
    audit: [],
    projects: [],
    lastIdempotencyKey: null,
  };

  // -------------------------------------------------------------------------
  // DOM refs (cached after first render)
  // -------------------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const announcer = $("#announcer");
  const main = $("#main");
  const navEl = $("#main-nav");
  const signoutBtn = $("#signout-btn");
  const langToggle = $("#lang-toggle");
  const authBanner = $("#auth-banner");

  // -------------------------------------------------------------------------
  // i18n
  // -------------------------------------------------------------------------
  async function loadLocales() {
    const promises = SUPPORTED_LANGS.map((lng) =>
      fetch(`/locales/${lng}.json`)
        .then((r) => (r.ok ? r.json() : {}))
        .catch(() => ({}))
    );
    const [en, fr, es] = await Promise.all(promises);
    state.locales = { en, fr, es };
    // Fallback any missing keys to English.
    SUPPORTED_LANGS.forEach((lng) => {
      if (lng !== "en") {
        const base = state.locales.en;
        const cur = state.locales[lng];
        Object.keys(base).forEach((k) => {
          if (!(k in cur)) cur[k] = base[k];
        });
      }
    });
  }

  function t(key, params = {}) {
    const strings = state.locales[state.lang] || state.locales.en;
    let text = strings[key] || key;
    Object.keys(params).forEach((p) => {
      text = text.replace(new RegExp(`\\{${p}\\}`, "g"), params[p]);
    });
    return text;
  }

  function setLang(lng) {
    if (!SUPPORTED_LANGS.includes(lng)) return;
    state.lang = lng;
    document.documentElement.lang = lng;
    document.documentElement.setAttribute("data-i18n-lang", lng);
    // Update lang toggle aria-pressed.
    $$(".language-button").forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.lang === lng);
    });
    translatePage();
    updateShell();
    announce(t("nav.langSwitch") + ": " + LANG_LABELS[lng]);
  }

  const LANG_LABELS = { en: "English", fr: "Français", es: "Español" };

  function translatePage() {
    // data-i18n -> textContent
    $$("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    // data-i18n-placeholder
    $$("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    // data-i18n-label -> aria-label
    $$("[data-i18n-label]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nLabel));
    });
    // data-i18n-title
    $$("[data-i18n-title]").forEach((el) => {
      el.title = t(el.dataset.i18nTitle);
    });
    // data-i18n-value
    $$("[data-i18n-value]").forEach((el) => {
      el.value = t(el.dataset.i18nValue);
    });
    // Update option labels that carry data-i18n.
    $$("option[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.title = t("app.name");
  }

  function announce(msg) {
    if (!msg) return;
    announcer.textContent = "";
    // Small delay lets screen readers pick up an empty->text change.
    setTimeout(() => {
      announcer.textContent = msg;
    }, 20);
  }

  // -------------------------------------------------------------------------
  // Date / time helpers (UTC-backed, IANA timezone display, DST-safe)
  // -------------------------------------------------------------------------
  function parseUtc(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function formatUtc(iso, timeZone = "UTC") {
    const d = parseUtc(iso);
    if (!d) return "—";
    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone,
      timeZoneName: "longOffset",
    }).format(d);
  }

  function formatUtcShort(iso) {
    const d = parseUtc(iso);
    if (!d) return "—";
    return d.toISOString().replace("Z", " UTC");
  }

  function localTz() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  function toLocalISO(date) {
    // Convert a Date to local "YYYY-MM-DDTHH:MM" for datetime-local inputs.
    if (!(date instanceof Date)) date = new Date();
    const tzOffset = date.getTimezoneOffset() * 60000;
    const local = new Date(date.getTime() - tzOffset);
    return local.toISOString().slice(0, 16);
  }

  // -------------------------------------------------------------------------
  // API client (bearer token + idempotency keys)
  // -------------------------------------------------------------------------
  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    // Idempotency key for mutating methods, unless caller supplied one.
    if (options.method && !/^GET$/i.test(options.method) && !headers["Idempotency-Key"]) {
      headers["Idempotency-Key"] = `eqt_${crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`;
    }
    state.lastIdempotencyKey = headers["Idempotency-Key"] || null;

    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (err) {
      throw new Error(t("error.network"));
    }

    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }

    if (!response.ok) {
      const detail = data.detail || data.msg || `HTTP ${response.status}`;
      let msg = t("error.unknown");
      if (response.status === 401) msg = t("error.unauthorized");
      else if (response.status === 403) msg = t("error.forbidden");
      else if (response.status === 404) msg = t("error.notFound");
      else if (response.status === 409) msg = detail;
      else if (response.status === 422) msg = detail;
      else if (response.status >= 500) msg = t("error.server");
      const err = new Error(msg);
      err.status = response.status;
      err.detail = detail;
      err.data = data;
      throw err;
    }
    return data;
  }

  function requireAuth() {
    return !!state.token;
  }

  function setToken(token, user) {
    state.token = token;
    state.user = user;
    if (user) state.role = user.role;
    try {
      sessionStorage.setItem(STORAGE_KEY, token);
      sessionStorage.setItem("equitask_user", JSON.stringify(user));
    } catch (e) {
      // storage may be blocked; continue in-memory only.
    }
    updateShell();
  }

  function clearToken() {
    state.token = null;
    state.user = null;
    state.role = null;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem("equitask_user");
    } catch (e) {}
    updateShell();
  }

  function restoreSession() {
    try {
      const tok = sessionStorage.getItem(STORAGE_KEY);
      const usr = sessionStorage.getItem("equitask_user");
      if (tok) state.token = tok;
      if (usr) state.user = JSON.parse(usr);
      if (state.user) state.role = state.user.role;
    } catch (e) {}
  }

  // -------------------------------------------------------------------------
  // Shell (header nav, auth banner, signout)
  // -------------------------------------------------------------------------
  function updateShell() {
    const authed = !!state.token;
    signoutBtn.hidden = !authed;
    signoutBtn.disabled = !authed;
    langToggle.hidden = false;

    // Role-based navigation.
    const links = [];
    if (authed) {
      links.push({ route: "volunteer-dashboard", label: t("nav.volunteerDashboard"), role: "VOLUNTEER" });
      links.push({ route: "org-dashboard", label: t("nav.orgDashboard"), role: "ORGANIZATION" });
      links.push({ route: "coordinator-dashboard", label: t("nav.coordinatorDashboard"), role: "COORDINATOR" });
      links.push({ route: "admin-dashboard", label: t("nav.adminDashboard"), role: "ADMIN" });
      links.push({ route: "profile", label: t("nav.profile") });
    } else {
      links.push({ route: "login", label: t("nav.login") });
      links.push({ route: "register", label: t("nav.register") });
    }

    // Filter by user role: show dashboards matching the user's role plus profile.
    const allowedRoles = authed ? [state.role] : null;
    const html = links
      .filter((l) => !allowedRoles || l.route === "profile" || l.route === "login" || l.route === "register" || l.role === allowedRoles[0])
      .map(
        (l) =>
          `<a href="#/${l.route}" class="nav-link${location.hash === "#/" + l.route ? " nav-link--active" : ""}">${l.label}</a>`
      )
      .join(" ");
    navEl.innerHTML = html;
    // Re-apply i18n for any nav links not covered by data-i18n (the label is already set above).

    if (authed) {
      authBanner.innerHTML = `<span class="badge badge--verified">${t("auth.signedIn")}</span> <strong>${escapeHtml(state.user.display_name)}</strong> (${state.user.role})`;
    } else {
      authBanner.innerHTML = "";
    }
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }

  // -------------------------------------------------------------------------
  // Form helpers
  // -------------------------------------------------------------------------
  function showFieldError(formId, fieldId, message) {
    const el = $(`#${fieldId}-error`);
    if (el) el.textContent = message || "";
  }

  function clearFieldErrors(formId) {
    $$(`#${formId} .field-error`).forEach((el) => (el.textContent = ""));
  }

  function validateForm(formElement, rules) {
    // rules: { name: { required, email, min, max, match, minlength } }
    const errors = {};
    const formData = new FormData(formElement);
    Object.keys(rules).forEach((field) => {
      const value = formData.get(field) || "";
      const rule = rules[field] || {};
      if (rule.required && String(value).trim() === "") {
        errors[field] = t("common.required");
        return;
      }
      if (value !== "" && rule.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value))) {
        errors[field] = "Enter a valid email address.";
        return;
      }
      if (rule.minlength && String(value).length < rule.minlength) {
        errors[field] = `At least ${rule.minlength} characters.`;
        return;
      }
      if (rule.match) {
        const other = formData.get(rule.match);
        if (String(value) !== String(other)) errors[field] = "Passwords do not match.";
      }
      if (rule.min !== undefined && value !== "" && Number(value) < rule.min) {
        errors[field] = `Minimum ${rule.min}.`;
      }
      if (rule.max !== undefined && value !== "" && Number(value) > rule.max) {
        errors[field] = `Maximum ${rule.max}.`;
      }
    });
    return { valid: Object.keys(errors).length === 0, errors, data: Object.fromEntries(formData) };
  }

  function setButtonLoading(button, loading) {
    if (!button) return;
    if (loading) {
      button.classList.add("button--loading");
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    } else {
      button.classList.remove("button--loading");
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  function showMessage(containerId, message, type = "error") {
    const el = $(`#${containerId}`);
    if (!el) return;
    el.className = `message message--${type}`;
    el.textContent = message;
    el.hidden = false;
    announce(message);
    if (type === "success") {
      setTimeout(() => {
        el.hidden = true;
        el.textContent = "";
      }, 5000);
    }
  }

  function hideMessage(containerId) {
    const el = $(`#${containerId}`);
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
  }

  // -------------------------------------------------------------------------
  // Generic list renderer
  // -------------------------------------------------------------------------
  function renderList(containerId, items, renderRow, emptyMsgKey = "common.none") {
    const el = $(containerId);
    if (!el) return;
    if (!items || items.length === 0) {
      el.innerHTML = `<p class="empty">${t(emptyMsgKey)}</p>`;
      return;
    }
    el.innerHTML = items.map(renderRow).join("");
  }

  // -------------------------------------------------------------------------
  // Status badge
  // -------------------------------------------------------------------------
  function badgeFor(stateValue) {
    const map = {
      OFFERED: "offered",
      ACCEPTED: "accepted",
      DECLINED: "declined",
      EXPIRED: "expired",
      PENDING_APPROVAL: "pendingApproval",
      ACTIVE: "active",
      SUBMITTED: "submitted",
      UNDER_REVIEW: "underReview",
      COMPLETED: "completed",
      DISPUTED: "disputed",
      WITHDRAWN: "withdrawn",
      DRAFT: "draft",
      VALIDATED: "validated",
      PENDING: "pending",
    };
    const key = map[stateValue] || stateValue.toLowerCase();
    return `<span class="badge badge--${key}">${t(`status.${key}`) || stateValue}</span>`;
  }

  // -------------------------------------------------------------------------
  // Router
  // -------------------------------------------------------------------------
  function currentRoute() {
    const hash = location.hash || "#/login";
    const path = hash.replace(/^#\/?/, "").split("?")[0] || "login";
    return path;
  }

  function navigate(route) {
    location.hash = `#/${route}`;
  }

  function requireRole(allowedRoles) {
    if (!state.token) {
      navigate("login");
      announce(t("error.unauthorized"));
      return false;
    }
    if (allowedRoles && !allowedRoles.includes(state.role)) {
      announce(t("error.forbidden"));
      navigate(roleRoute(state.role));
      return false;
    }
    return true;
  }

  function roleRoute(role) {
    const map = {
      VOLUNTEER: "volunteer-dashboard",
      ORGANIZATION: "org-dashboard",
      COORDINATOR: "coordinator-dashboard",
      ADMIN: "admin-dashboard",
    };
    return map[role] || "login";
  }

  async function route() {
    const routeName = currentRoute();
    $$(".page").forEach((p) => (p.hidden = true));
    const page = $(`#page-${routeName}`);
    if (page) page.hidden = false;
    main.focus();
    announce(`Page: ${t(`nav.${routeName.replace(/-/g, "")}`) || routeName}`);
    updateShell();

    // Auth-gated routes.
    const publicRoutes = ["login", "register"];
    if (!publicRoutes.includes(routeName) && !state.token) {
      navigate("login");
      return;
    }

    try {
      switch (routeName) {
        case "login":
          initLogin();
          break;
        case "register":
          initRegister();
          break;
        case "volunteer-dashboard":
          if (!requireRole(["VOLUNTEER", "ADMIN"])) return;
          initVolunteerDashboard();
          break;
        case "org-dashboard":
          if (!requireRole(["ORGANIZATION", "COORDINATOR", "ADMIN"])) return;
          initOrgDashboard();
          break;
        case "coordinator-dashboard":
          if (!requireRole(["COORDINATOR", "ADMIN"])) return;
          initCoordinatorDashboard();
          break;
        case "admin-dashboard":
          if (!requireRole(["ADMIN"])) return;
          initAdminDashboard();
          break;
        case "profile":
          if (!requireRole()) return;
          initProfile();
          break;
        default:
          navigate("login");
      }
    } catch (err) {
      console.error(err);
      announce(t("error.unknown"));
    }
  }

  // -------------------------------------------------------------------------
  // Login page
  // -------------------------------------------------------------------------
  async function initLogin() {
    const form = $("#form-login");
    const submit = $("#login-submit");
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      clearFieldErrors("form-login");
      hideMessage("login-message");
      const { valid, errors, data } = validateForm(form, {
        email: { required: true, email: true },
        password: { required: true },
      });
      if (!valid) {
        Object.entries(errors).forEach(([f, m]) => showFieldError("form-login", `${f}`, m));
        return;
      }
      setButtonLoading(submit, true);
      try {
        const tokenData = await api("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: data.email, password: data.password }),
        });
        // Fetch /me to get the real user record (role, display_name).
        const me = await api("/me");
        setToken(tokenData.access_token, me);
        hideMessage("login-message");
        showMessage("login-message", t("auth.signedIn"), "success");
        setTimeout(() => navigate(roleRoute(state.role || "VOLUNTEER")), 600);
      } catch (err) {
        showMessage("login-message", err.detail || t("auth.signInFailed"), "error");
      } finally {
        setButtonLoading(submit, false);
      }
    };
  }

  // -------------------------------------------------------------------------
  // Register page
  // -------------------------------------------------------------------------
  async function initRegister() {
    const form = $("#form-register");
    const submit = $("#reg-submit");
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      clearFieldErrors("form-register");
      hideMessage("register-message");
      const { valid, errors, data } = validateForm(form, {
        role: { required: true },
        email: { required: true, email: true },
        password: { required: true, minlength: 10, match: "password2" },
        password2: { required: true },
        display_name: { required: true },
      });
      if (!valid) {
        Object.entries(errors).forEach(([f, m]) => showFieldError("form-register", `reg-${f}`, m));
        return;
      }
      setButtonLoading(submit, true);
      try {
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            email: data.email,
            password: data.password,
            role: data.role,
            display_name: data.display_name,
          }),
        });
        hideMessage("register-message");
        showMessage("register-message", t("auth.registered"), "success");
        setTimeout(() => navigate("login"), 800);
      } catch (err) {
        showMessage("register-message", err.detail || t("auth.registerFailed"), "error");
      } finally {
        setButtonLoading(submit, false);
      }
    };
  }

  // -------------------------------------------------------------------------
  // Volunteer dashboard
  // -------------------------------------------------------------------------
  async function initVolunteerDashboard() {
    const welcome = $("#vd-welcome");
    if (state.user) welcome.textContent = t("volunteer.welcome", { name: state.user.display_name || state.user.email });

    // Load /me and volunteer profile.
    try {
      const me = await api("/me");
      state.user = me;
      state.role = me.role;
      welcome.textContent = t("volunteer.welcome", { name: me.display_name || me.email });
    } catch (e) {
      welcome.textContent = t("volunteer.welcome", { name: state.user.display_name || "volunteer" });
    }

    try {
      const vol = await api("/volunteers/me");
      state.volunteer = vol;
      renderVolunteerProfile(vol);
    } catch (e) {
      // Profile may not exist yet; show empty state.
      state.volunteer = null;
      renderVolunteerProfile(null);
    }

    // Load proposals (opportunities).
    try {
      const props = await api("/proposals");
      state.proposals = Array.isArray(props) ? props : [];
      renderVolunteerProposals(state.proposals);
    } catch (e) {
      renderVolunteerProposals([]);
      showMessage("vd-message", `Could not load proposals: ${e.detail || e.message}`, "error");
    }

    renderVolunteerAssignments();

    // ---- Skills form ----
    const skillsForm = $("#form-vd-skills");
    skillsForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(skillsForm);
      const skill = fd.get("skill").trim();
      const proficiency = Number(fd.get("proficiency"));
      const stateVal = fd.get("state");
      if (!skill) return;
      const facts = [{ skill, proficiency: Number.isFinite(proficiency) ? proficiency : 0, state: stateVal, source: "self_report", observed_at: new Date().toISOString() }];
      try {
        await api("/volunteers/me/skills", { method: "POST", body: JSON.stringify({ skills: facts }) });
        state.skills.push(...facts);
        renderVolunteerSkills();
        skillsForm.reset();
        showMessage("vd-message", t("volunteer.skillAdded"), "success");
      } catch (err) {
        showMessage("vd-message", err.detail || t("error.unknown"), "error");
      }
    };

    // ---- Availability form ----
    const availForm = $("#form-vd-avail");
    availForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(availForm);
      const start = fd.get("start_utc");
      const end = fd.get("end_utc");
      if (!start || !end) return;
      try {
        await api("/volunteers/me/availability", {
          method: "POST",
          body: JSON.stringify({ start_utc: start, end_utc: end, state: "KNOWN_TRUE" }),
        });
        state.availability.push({ start_utc: start, end_utc: end, state: "KNOWN_TRUE" });
        renderVolunteerAvailability();
        availForm.reset();
        // Pre-fill next start from today.
        $("#vd-avail-start").value = toLocalISO(new Date());
        showMessage("vd-message", t("volunteer.availabilityAdded"), "success");
      } catch (err) {
        showMessage("vd-message", err.detail || t("error.unknown"), "error");
      }
    };

    // ---- Language form ----
    const langForm = $("#form-vd-lang");
    langForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(langForm);
      const language = fd.get("language").trim();
      if (!language) return;
      // Preferences endpoint uses task_type "language:<lang>".
      try {
        await api("/volunteers/me/preferences", {
          method: "POST",
          body: JSON.stringify({ preferences: { [`language:${language}`]: "KNOWN_TRUE" } }),
        });
        state.languages.push(language);
        renderVolunteerLanguages();
        langForm.reset();
        showMessage("vd-message", "Language saved.", "success");
      } catch (err) {
        showMessage("vd-message", err.detail || t("error.unknown"), "error");
      }
    };

    // ---- Preference form ----
    const prefForm = $("#form-vd-pref");
    prefForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(prefForm);
      const taskType = fd.get("task_type").trim();
      const value = fd.get("value");
      if (!taskType) return;
      try {
        await api("/volunteers/me/preferences", {
          method: "POST",
          body: JSON.stringify({ preferences: { [taskType]: value } }),
        });
        state.preferences[taskType] = value;
        renderVolunteerPreferences();
        prefForm.reset();
        showMessage("vd-message", t("volunteer.preferenceSaved"), "success");
      } catch (err) {
        showMessage("vd-message", err.detail || t("error.unknown"), "error");
      }
    };

    // ---- Edit profile (inline) ----
    const editBtn = $("#vd-edit-profile");
    editBtn.onclick = () => {
      const vol = state.volunteer;
      if (!vol) {
        showMessage("vd-message", "Create a volunteer profile first (register as a volunteer).", "info");
        return;
      }
      const display = prompt(t("volunteer.displayName"), vol.display_name);
      if (display === null) return;
      const tz = prompt(t("volunteer.timezone"), vol.timezone || "UTC");
      if (tz === null) return;
      const cap = prompt(t("volunteer.weeklyCapacity"), vol.weekly_capacity_hours);
      if (cap === null) return;
      const contact = confirm(t("volunteer.contactPermitted"));
      const payload = {};
      if (display) payload.display_name = display;
      if (tz) payload.timezone = tz;
      if (cap !== null && cap !== "") payload.weekly_capacity_hours = Number(cap);
      payload.contact_permitted = contact;
      api("/volunteers/me", { method: "PATCH", body: JSON.stringify(payload) })
        .then((updated) => {
          state.volunteer = updated;
          renderVolunteerProfile(updated);
          showMessage("vd-message", t("volunteer.profileUpdated"), "success");
        })
        .catch((err) => showMessage("vd-message", err.detail || t("error.unknown"), "error"));
    };
  }

  function renderVolunteerProfile(vol) {
    const fields = {
      "vd-name": vol ? vol.display_name : "—",
      "vd-tz": vol ? vol.timezone : "—",
      "vd-capacity": vol ? vol.weekly_capacity_hours : "—",
      "vd-country": vol ? (vol.country_code || "—") : "—",
      "vd-contact": vol ? (vol.contact_permitted ? t("yes") : t("no")) : "—",
    };
    Object.entries(fields).forEach(([id, val]) => {
      const el = $(`#${id}`);
      if (el) el.textContent = val;
    });
    renderVolunteerSkills();
    renderVolunteerAvailability();
    renderVolunteerLanguages();
    renderVolunteerPreferences();
  }

  function renderVolunteerSkills() {
    const list = $("#vd-skills-list");
    if (!list) return;
    if (!state.skills || state.skills.length === 0) {
      list.innerHTML = `<p class="empty">${t("common.none")}</p>`;
      return;
    }
    const ksLabels = { KNOWN_TRUE: "volunteer.ksKnown", UNKNOWN: "volunteer.ksUnknown", STALE: "volunteer.ksStale" };
    list.innerHTML = state.skills
      .map(
        (s) =>
          `<div class="kv"><span class="k">${escapeHtml(s.skill)}</span><span class="v">${s.proficiency} — ${t(ksLabels[s.state]) || s.state}</span></div>`
      )
      .join("");
  }

  function renderVolunteerAvailability() {
    const list = $("#vd-avail-list");
    if (!list) return;
    if (!state.availability || state.availability.length === 0) {
      list.innerHTML = `<p class="empty">${t("common.none")}</p>`;
      return;
    }
    list.innerHTML = state.availability
      .map((a) => `<div class="kv"><span class="k">${formatUtc(a.start_utc)}</span><span class="v">${formatUtc(a.end_utc)}</span></div>`)
      .join("");
  }

  function renderVolunteerLanguages() {
    const list = $("#vd-lang-list");
    if (!list) return;
    if (!state.languages || state.languages.length === 0) {
      list.innerHTML = `<p class="empty">${t("common.none")}</p>`;
      return;
    }
    list.innerHTML = state.languages.map((l) => `<span class="badge">${escapeHtml(l)}</span>`).join(" ");
  }

  function renderVolunteerPreferences() {
    const list = $("#vd-pref-list");
    if (!list) return;
    const prefs = state.preferences;
    const keys = Object.keys(prefs);
    if (!list || keys.length === 0) {
      if (list) list.innerHTML = `<p class="empty">${t("common.none")}</p>`;
      return;
    }
    list.innerHTML = keys
      .map((k) => `<div class="kv"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(prefs[k])}</span></div>`)
      .join("");
  }

  function renderVolunteerProposals(props) {
    const list = $("#vd-proposals-list");
    if (!list) return;
    if (!props || props.length === 0) {
      list.innerHTML = `<p class="empty">${t("volunteer.noProposals")}</p>`;
      return;
    }
    list.innerHTML = props
      .map(
        (p) =>
          `<article class="card" style="padding:0.75rem 1rem;">
            <div class="kv"><span class="k">Task</span><span class="v">${escapeHtml(p.task_id)}</span></div>
            <div class="kv"><span class="k">Proposal</span><span class="v">${escapeHtml(p.id)}</span></div>
            <div class="kv"><span class="k">State</span><span class="v">${badgeFor(p.state)}</span></div>
            <div class="kv"><span class="k">Fit</span><span class="v">${p.fit_score ?? "—"}</span></div>
            <div class="kv"><span class="k">Risk</span><span class="v">${p.risk_score ?? "—"}</span></div>
            ${p.state === "OFFERED"
              ? `<div class="button-group" style="margin-top:0.5rem;">
                  <button class="button button--primary btn-accept" data-id="${escapeHtml(p.id)}" data-task="${escapeHtml(p.task_id)}">${t("volunteer.accept")}</button>
                  <button class="button button--ghost btn-decline" data-id="${escapeHtml(p.id)}" data-task="${escapeHtml(p.task_id)}">${t("volunteer.decline")}</button>
                </div>`
              : `<p class="hint">Decision already recorded.</p>`
            }
          </article>`
      )
      .join("");
    // Wire accept/decline.
    $$(".btn-accept").forEach((btn) => {
      btn.onclick = () => respondProposal(btn.dataset.id, "accept");
    });
    $$(".btn-decline").forEach((btn) => {
      btn.onclick = () => respondProposal(btn.dataset.id, "decline");
    });
  }

  async function respondProposal(proposalId, action) {
    const reason = prompt(`Reason for ${action} (optional):`);
    try {
      const result = await api(`/proposals/${proposalId}/respond`, {
        method: "POST",
        body: JSON.stringify({ action, reason }),
      });
      announce(t(`volunteer.consent${action.charAt(0).toUpperCase() + action.slice(1)}`));
      showMessage("vd-message", `Proposal ${action}ed. ${result.status}`, "success");
      // Refresh proposals.
      const props = await api("/proposals");
      state.proposals = Array.isArray(props) ? props : [];
      renderVolunteerProposals(state.proposals);
      renderVolunteerAssignments();
    } catch (err) {
      showMessage("vd-message", err.detail || t("error.unknown"), "error");
    }
  }

  // Assignments / deliverables (simulated — backend has no assignment list or deliverable endpoint).
  function renderVolunteerAssignments() {
    const list = $("#vd-assignments-list");
    if (!list) return;
    const accepted = (state.proposals || []).filter((p) => p.state === "ACCEPTED");
    if (!accepted.length) {
      list.innerHTML = `<p class="empty">${t("volunteer.noAssignments")}</p>`;
      return;
    }
    list.innerHTML = accepted
      .map(
        (p) =>
          `<article class="card" style="padding:0.75rem 1rem;">
            <div class="kv"><span class="k">Task</span><span class="v">${escapeHtml(p.task_id)}</span></div>
            <div class="kv"><span class="k">Proposal</span><span class="v">${escapeHtml(p.id)}</span></div>
            <div class="kv"><span class="k">State</span><span class="v">${badgeFor("ACCEPTED")}</span></div>
            <div class="button-group" style="margin-top:0.5rem;">
              <button class="button button--primary btn-deliverable" data-id="${escapeHtml(p.id)}" data-task="${escapeHtml(p.task_id)}">${t("volunteer.submitDeliverable")}</button>
              <button class="button button--ghost btn-withdraw-sim" data-id="${escapeHtml(p.id)}">${t("volunteer.withdraw")}</button>
            </div>
            <p class="hint" style="margin-top:0.4rem;">${t("error.demoEndpoint")}</p>
          </article>`
      )
      .join("");
    $$(".btn-deliverable").forEach((btn) => {
      btn.onclick = () => submitDeliverableSim(btn.dataset.id, btn.dataset.task);
    });
    $$(".btn-withdraw-sim").forEach((btn) => {
      btn.onclick = () => withdrawSim(btn.dataset.id);
    });
  }

  async function submitDeliverableSim(proposalId, taskId) {
    const link = prompt(t("volunteer.deliverableLink"));
    if (link === null) return;
    const notes = prompt(t("volunteer.deliverableNotes"));
    // Attempt a (non-existent) backend endpoint honestly, then fall back to local record.
    try {
      await api(`/assignments/${proposalId}/deliverables`, {
        method: "POST",
        body: JSON.stringify({ link, notes }),
      });
      showMessage("vd-message", t("volunteer.deliverableSubmitted"), "success");
      return;
    } catch (err) {
      if (err.status === 404) {
        // Simulate locally.
        state.deliverables = state.deliverables || [];
        state.deliverables.push({ proposalId, taskId, link, notes, submittedAt: new Date().toISOString() });
        showMessage("vd-message", t("error.demoEndpoint"), "info");
        announce(t("volunteer.deliverableSubmitted"));
        return;
      }
      showMessage("vd-message", err.detail || t("error.unknown"), "error");
    }
  }

  async function withdrawSim(proposalId) {
    if (!confirm(t("volunteer.withdraw"))) return;
    try {
      await api(`/proposals/${proposalId}/respond`, {
        method: "POST",
        body: JSON.stringify({ action: "decline", reason: "Volunteer withdrawal (simulated)" }),
      });
      showMessage("vd-message", t("volunteer.consentWithdrawn"), "success");
      const props = await api("/proposals");
      state.proposals = Array.isArray(props) ? props : [];
      renderVolunteerProposals(state.proposals);
      renderVolunteerAssignments();
    } catch (err) {
      // Fall back to local simulation.
      showMessage("vd-message", t("error.demoEndpoint"), "info");
      announce(t("volunteer.consentWithdrawn"));
    }
  }

  // -------------------------------------------------------------------------
  // Organization dashboard
  // -------------------------------------------------------------------------
  async function initOrgDashboard() {
    if (state.user) {
      $("#od-welcome").textContent = t("org.welcome");
    }
    try {
      const me = await api("/me");
      state.user = me;
    } catch (e) {}

    // Create organization (POST /organizations).
    const orgCreateForm = $("#form-org-create");
    orgCreateForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(orgCreateForm);
      const name = fd.get("name").trim();
      const country = fd.get("country_code").trim() || undefined;
      const evidence = fd.get("evidence_ref").trim() || undefined;
      if (!name) return;
      try {
        const created = await api("/organizations", {
          method: "POST",
          body: JSON.stringify({ name, country_code: country, evidence_ref: evidence }),
        });
        state.currentOrgId = created.id;
        $("#od-org-name").textContent = created.name;
        $("#od-org-status").textContent = t("org.statusPending");
        $("#od-org-status").className = "badge badge--pending";
        $("#od-org-country").textContent = created.country_code || "—";
        $("#od-org-id").textContent = created.id;
        orgCreateForm.reset();
        showMessage("od-message", t("org.created"), "success");
        announce(t("org.created"));
        renderOrgProjectSelect();
      } catch (err) {
        showMessage("od-message", err.detail || t("org.createFailed"), "error");
      }
    };

    // Load projects / proposals.
    renderOrgProjects();
    renderOrgProposals();

    // ---- Create project ----
    const projForm = $("#form-od-project");
    projForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(projForm);
      const orgId = state.currentOrgId;
      if (!orgId) {
        showMessage("od-message", "Create or select an organization first.", "error");
        return;
      }
      try {
        const created = await api("/projects", {
          method: "POST",
          body: JSON.stringify({ organization_id: orgId, name: fd.get("name"), description: fd.get("description") || "" }),
        });
        state.projects.push(created);
        renderOrgProjects();
        projForm.reset();
        showMessage("od-message", t("org.projectCreated"), "success");
      } catch (err) {
        showMessage("od-message", err.detail || t("org.createFailed"), "error");
      }
    };

    // ---- Create task ----
    const taskForm = $("#form-od-task");
    // Pre-fill now+3days for start/end, +4 days deadline.
    const now = new Date();
    const startDefault = toLocalISO(new Date(now.getTime() + 2 * 86400000));
    const endDefault = toLocalISO(new Date(now.getTime() + 5 * 86400000));
    const deadlineDefault = toLocalISO(new Date(now.getTime() + 6 * 86400000));
    $("#od-task-start").value = startDefault;
    $("#od-task-end").value = endDefault;
    $("#od-task-deadline").value = deadlineDefault;

    taskForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(taskForm);
      const projectId = fd.get("project_id");
      if (!projectId) {
        showMessage("od-message", "Select a project.", "error");
        return;
      }
      const skillsRaw = fd.get("required_skills") || "";
      const requiredSkills = skillsRaw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => {
          const [name, min] = s.split(":");
          return { skill: name.trim(), min_proficiency: Number(min) || 0, mandatory: true };
        });
      const langsRaw = fd.get("required_languages") || "";
      const requiredLanguages = langsRaw.split(",").map((s) => s.trim()).filter(Boolean);
      try {
        const created = await api("/tasks", {
          method: "POST",
          body: JSON.stringify({
            project_id: projectId,
            name: fd.get("name"),
            description: fd.get("description") || "",
            required_skills: requiredSkills,
            effort_hours: Number(fd.get("effort_hours")) || 4,
            start_utc: fd.get("start_utc"),
            end_utc: fd.get("end_utc"),
            deadline_utc: fd.get("deadline_utc"),
            dependencies: [],
            max_assignees: Number(fd.get("max_assignees")) || 1,
            value: 100,
            acceptance_criteria_present: fd.get("acceptance_criteria") === "on",
            required_languages: requiredLanguages,
            requires_approval: fd.get("requires_approval") === "on",
          }),
        });
        showMessage("od-message", t("org.taskCreated"), "success");
        taskForm.reset();
        $("#od-task-start").value = startDefault;
        $("#od-task-end").value = endDefault;
        $("#od-task-deadline").value = deadlineDefault;
      } catch (err) {
        showMessage("od-message", err.detail || t("error.unknown"), "error");
      }
    };

    // Project selector for task form.
    renderOrgProjectSelect();
  }

  state.currentOrgId = null;

  async function renderOrgProjects() {
    // No GET /projects endpoint exists; show simulated list seeded from create actions.
    const list = $("#od-projects-list");
    if (!list) return;
    if (!state.projects || state.projects.length === 0) {
      list.innerHTML = `<p class="empty">${t("org.noProjects")}</p>`;
      return;
    }
    list.innerHTML = state.projects
      .map(
        (p) =>
          `<div class="kv"><span class="k">${escapeHtml(p.name)}</span><span class="v">${escapeHtml(p.id)}</span></div>`
      )
      .join("");
  }

  async function renderOrgProjectSelect() {
    const sel = $("#od-task-proj");
    if (!sel) return;
    sel.innerHTML = `<option value="" disabled selected>${t("common.none")}</option>`;
    (state.projects || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = p.name;
      sel.appendChild(o);
    });
  }

  async function renderOrgProposals() {
    // We can't list all org proposals without a project id. Show a hint + per-project if available.
    const list = $("#od-proposals-list");
    if (!list) return;
    if (!state.currentOrgId) {
      list.innerHTML = `<p class="empty">Create an organization to see proposals.</p>`;
      return;
    }
    if (!state.projects?.length) {
      list.innerHTML = `<p class="empty">${t("org.noTasks")}</p>`;
      return;
    }
    // Fetch proposals for the first project (demo simplification).
    try {
      const props = await api(`/projects/${state.projects[0].id}/proposals`);
      renderList("#od-proposals-list", Array.isArray(props) ? props : [], renderOrgProposalRow, "org.noTasks");
    } catch (e) {
      list.innerHTML = `<p class="empty">Could not load proposals.</p>`;
    }
  }

  function renderOrgProposalRow(p) {
    return `<article class="card" style="padding:0.75rem 1rem;">
      <div class="kv"><span class="k">Task</span><span class="v">${escapeHtml(p.task_id)}</span></div>
      <div class="kv"><span class="k">Volunteer</span><span class="v">${escapeHtml(p.volunteer_id)}</span></div>
      <div class="kv"><span class="k">State</span><span class="v">${badgeFor(p.state)}</span></div>
      <div class="kv"><span class="k">Fit</span><span class="v">${p.fit_score ?? "—"}</span></div>
      <div class="button-group" style="margin-top:0.5rem;">
        <button class="button button--primary btn-org-approve" data-id="${escapeHtml(p.id)}">${t("org.approve")}</button>
        <button class="button button--ghost btn-org-clarify" data-id="${escapeHtml(p.id)}">${t("org.clarify")}</button>
        <button class="button button--ghost btn-org-reassign" data-id="${escapeHtml(p.id)}">${t("org.reassign")}</button>
      </div>
      <p class="hint" style="margin-top:0.4rem;">${t("error.demoEndpoint")}</p>
    </article>`;
  }

  // -------------------------------------------------------------------------
  // Coordinator dashboard
  // -------------------------------------------------------------------------
  async function initCoordinatorDashboard() {
    try {
      const me = await api("/me");
      state.user = me;
    } catch (e) {}

    // Project selector for allocation run.
    const projSel = $("#cd-project");
    projSel.innerHTML = `<option value="" disabled selected>${t("common.none")}</option>`;
    // Coordinator can't list projects either; simulate from state or allow manual entry.
    (state.projects || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = p.name;
      projSel.appendChild(o);
    });

    // Default occurred_at to now.
    $("#cd-occurred").value = toLocalISO(new Date());

    // ---- Run allocation ----
    const runForm = $("#form-cd-run");
    runForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(runForm);
      const projectId = fd.get("project_id");
      const mode = fd.get("mode");
      if (!projectId) {
        showMessage("cd-message", "Select a project.", "error");
        return;
      }
      setButtonLoading($("#cd-run-submit"), true);
      try {
        const result = await api("/allocations/run", {
          method: "POST",
          body: JSON.stringify({ project_id: projectId }),
        });
        showMessage("cd-message", t("coord.runComplete"), "success");
        renderCoordProposals(result.proposals || []);
        announce(`${t("coord.runComplete")} ${(result.proposals || []).length} proposals.`);
      } catch (err) {
        showMessage("cd-message", err.detail || t("error.unknown"), "error");
      } finally {
        setButtonLoading($("#cd-run-submit"), false);
      }
    };

    // ---- Record event (withdrawal / repair) ----
    const eventForm = $("#form-cd-event");
    eventForm.onsubmit = async (ev) => {
      ev.preventDefault();
      const fd = new FormData(eventForm);
      const eventType = fd.get("event_type");
      const assignmentId = fd.get("assignment_id") || undefined;
      const occurredAt = fd.get("occurred_at");
      const note = fd.get("note") || undefined;
      if (eventType === "WITHDRAWAL" && !assignmentId) {
        showMessage("cd-message", "Assignment ID required for withdrawal.", "error");
        return;
      }
      if (!occurredAt) {
        showMessage("cd-message", "Please provide when it occurred.", "error");
        return;
      }
      setButtonLoading($("#cd-event-submit"), true);
      try {
        const result = await api("/events", {
          method: "POST",
          body: JSON.stringify({ event_type: eventType, assignment_id: assignmentId, occurred_at: occurredAt, note }),
        });
        showMessage("cd-message", t("coord.eventRecorded"), "success");
        const resEl = $("#cd-event-result");
        resEl.innerHTML = `
          <div class="kv"><span class="k">${t("coord.repairRun")}</span><span class="v">${result.repair_run_id || "—"}</span></div>
          <div class="kv"><span class="k">${t("coord.commitmentsKept", { count: result.kept_commitments ?? 0 })}</span><span class="v">${result.kept_commitments ?? 0}</span></div>
          <div class="kv"><span class="k">${t("coord.commitmentsReleased", { count: result.released_commitments ?? 0 })}</span><span class="v">${result.released_commitments ?? 0}</span></div>
          <div class="kv"><span class="k">New proposals</span><span class="v">${result.new_proposals ?? 0}</span></div>
          <p class="hint">${escapeHtml(result.note || "")}</p>
        `;
        announce(t("coord.eventRecorded"));
      } catch (err) {
        showMessage("cd-message", err.detail || t("error.unknown"), "error");
      } finally {
        setButtonLoading($("#cd-event-submit"), false);
      }
    };

    renderCoordProposals([]);
  }

  function renderCoordProposals(props) {
    const list = $("#cd-proposals-list");
    if (!list) return;
    if (!props || props.length === 0) {
      list.innerHTML = `<p class="empty">${t("coord.noRepairProposals")}</p>`;
      return;
    }
    renderList("#cd-proposals-list", props, (p) => `<article class="card" style="padding:0.75rem 1rem;">
      <div class="kv"><span class="k">Task</span><span class="v">${escapeHtml(p.task_id)}</span></div>
      <div class="kv"><span class="k">Volunteer</span><span class="v">${escapeHtml(p.volunteer_id)}</span></div>
      <div class="kv"><span class="k">State</span><span class="v">${badgeFor("OFFERED")}</span></div>
      <div class="kv"><span class="k">Fit</span><span class="v">${p.fit_score ?? "—"}</span></div>
      <div class="kv"><span class="k">Risk</span><span class="v">${p.risk_score ?? "—"}</span></div>
    </article>`);
  }

  // -------------------------------------------------------------------------
  // Admin dashboard
  // -------------------------------------------------------------------------
  async function initAdminDashboard() {
    try {
      const me = await api("/me");
      state.user = me;
    } catch (e) {}

    // ---- Verify organizations (simulated list + verify by id) ----
    renderAdminOrgs();

    // ---- Audit log ----
    const limitSel = $("#ad-audit-limit");
    const refreshBtn = $("#ad-audit-refresh");
    const loadAudit = async () => {
      try {
        const limit = Number(limitSel.value) || 50;
        const audit = await api(`/audit?limit=${limit}`);
        state.audit = Array.isArray(audit) ? audit : [];
        renderAdminAudit(state.audit);
      } catch (err) {
        $("#ad-audit-list").innerHTML = `<p class="empty">Could not load audit log: ${err.detail || err.message}</p>`;
      }
    };
    refreshBtn.onclick = loadAudit;
    limitSel.onchange = loadAudit;
    loadAudit();

    // ---- Manage users (simulated) ----
    renderAdminUsers();

    // Org verify form is inline; wire the verify buttons after render.
  }

  function renderAdminOrgs() {
    const list = $("#ad-orgs-list");
    if (!list) return;
    // Simulated orgs (backend has no GET /organizations). Provide a verify-by-id input instead.
    list.innerHTML = `
      <div class="form-field" style="margin-bottom:0.5rem;">
        <label for="ad-org-id">Organization ID to verify</label>
        <input id="ad-org-id" type="text" placeholder="org_..." />
      </div>
      <button class="button button--primary" id="ad-org-verify">${t("admin.verify")}</button>
      <p class="hint">${t("error.demoEndpoint")}</p>
      <p class="empty">Backend exposes org verification by ID; no org list endpoint exists in this slice.</p>
    `;
    $("#ad-org-verify").onclick = async () => {
      const orgId = $("#ad-org-id").value.trim();
      if (!orgId) return;
      try {
        await api(`/admin/organizations/${orgId}/verify`, { method: "POST" });
        showMessage("ad-message", t("admin.verified"), "success");
        announce(t("admin.verified"));
      } catch (err) {
        showMessage("ad-message", err.detail || t("admin.verifyFailed"), "error");
      }
    };
  }

  function renderAdminAudit(audit) {
    const list = $("#ad-audit-list");
    if (!list) return;
    if (!audit || audit.length === 0) {
      list.innerHTML = `<p class="empty">${t("admin.noAudit")}</p>`;
      return;
    }
    list.innerHTML = `
      <table>
        <thead><tr><th>${t("admin.time")}</th><th>${t("admin.actor")}</th><th>${t("admin.action")}</th><th>${t("admin.target")}</th><th>${t("admin.reason")}</th></tr></thead>
        <tbody>
          ${audit.map((a) => `<tr><td>${formatUtc(a.created_at)}</td><td>${escapeHtml(a.actor_id || "—")}</td><td>${escapeHtml(a.action)}</td><td>${escapeHtml(a.target_type)} / ${escapeHtml(a.target_id)}</td><td>${escapeHtml(a.reason || "—")}</td></tr>`).join("")}
        </tbody>
      </table>`;
  }

  function renderAdminUsers() {
    const list = $("#ad-users-list");
    if (!list) return;
    list.innerHTML = `<p class="empty">${t("admin.noUsers")}</p><p class="hint">Backend exposes user registration and /me; no user list endpoint exists in this slice.</p>`;
  }

  // -------------------------------------------------------------------------
  // Profile page
  // -------------------------------------------------------------------------
  async function initProfile() {
    try {
      const me = await api("/me");
      state.user = me;
      state.role = me.role;
    } catch (e) {}
    const u = state.user || {};
    $("#pf-user").textContent = u.display_name || u.email || "—";
    $("#pf-role").textContent = u.role || "—";
  }

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------
  async function init() {
    await loadLocales();
    restoreSession();
    updateShell();

    // Language toggle in header.
    langToggle.onclick = () => {
      const current = state.lang;
      const idx = SUPPORTED_LANGS.indexOf(current);
      const next = SUPPORTED_LANGS[(idx + 1) % SUPPORTED_LANGS.length];
      setLang(next);
    };

    // Language buttons on profile page (delegated).
    document.addEventListener("click", (ev) => {
      if (ev.target.matches(".language-button")) {
        setLang(ev.target.dataset.lang);
      }
    });

    // Signout.
    signoutBtn.onclick = () => {
      if (confirm(t("auth.signOut"))) {
        clearToken();
        navigate("login");
        announce(t("auth.signOut"));
      }
    };

    // Router.
    window.addEventListener("hashchange", route);
    route();

    // Announce initial language.
    document.documentElement.lang = state.lang;
    document.documentElement.setAttribute("data-i18n-lang", state.lang);
    translatePage();
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", () => {
  EquiTask.init();
});
