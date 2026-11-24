"use strict";

const state = { token: null, projectId: null, lastResult: null };

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, { ...options, headers });
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

const $ = (id) => document.getElementById(id);

$("seed-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("seed-output").textContent = "Loading…";
  try {
    const data = await api("/demo/seed", {
      method: "POST",
      body: JSON.stringify({
        volunteers: Number($("seed-volunteers").value),
        tasks: Number($("seed-tasks").value),
        seed: 7,
      }),
    });
    state.projectId = data.project_id;
    $("project-id").value = data.project_id;
    $("seed-output").textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    $("seed-output").textContent = `Error: ${error.message}`;
  }
});

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("auth-status").textContent = "Signing in…";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: $("email").value, password: $("password").value }),
    });
    state.token = data.access_token;
    $("auth-status").textContent = "Signed in. Allocation is enabled.";
  } catch (error) {
    $("auth-status").textContent = `Sign-in failed: ${error.message}`;
  }
});

$("alloc-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.token) { $("alloc-output").textContent = "Sign in first."; return; }
  $("alloc-output").textContent = "Solving…";
  try {
    const result = await api("/allocations/run", {
      method: "POST",
      body: JSON.stringify({ project_id: $("project-id").value }),
    });
    state.lastResult = result;
    $("alloc-output").textContent = JSON.stringify(result, null, 2);
    const lines = [
      `Solver status: ${result.status}`,
      `Proposals: ${result.proposals.length}`,
      `Question count: ${result.questions.length}`,
      `Runtime: ${result.metrics ? result.metrics.solver_runtime_ms : "n/a"} ms`,
      ...result.messages,
    ];
    $("explain-output").textContent = lines.join("\n");
  } catch (error) {
    $("alloc-output").textContent = `Error: ${error.message}`;
  }
});
