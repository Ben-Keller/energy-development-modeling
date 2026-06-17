(function () {
  // Browser transport boundary for EDIM.
  //
  // This module owns API base URL selection, local test-user headers, downloads,
  // and low-level HTTP helpers. The React app builds model/workspace-specific
  // methods on top of this transport client.
  const USER_STORAGE_KEY = "edim.active_user_id";
  const API_MODE_STORAGE_KEY = "edim.api_target_mode";
  const LOCAL_API_BASE = inferLocalApiBase();
  const backendApiBase = normalizeApiBase(window.EDIM_BACKEND_API_BASE || "");

  let apiTargetMode = window.localStorage
    ? String(window.localStorage.getItem(API_MODE_STORAGE_KEY) || "local").toLowerCase()
    : "local";
  if (!["local", "backend"].includes(apiTargetMode)) apiTargetMode = "local";
  if (apiTargetMode === "backend" && !backendApiBase) apiTargetMode = "local";

  let activeUserId = window.localStorage
    ? window.localStorage.getItem(USER_STORAGE_KEY) || "undp_analyst"
    : "undp_analyst";

  function normalizeApiBase(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  function inferLocalApiBase() {
    const configured = normalizeApiBase(window.EDIM_LOCAL_API_BASE || window.EDIM_API_BASE || "");
    if (configured) return configured;
    const origin = normalizeApiBase(window.location.origin);
    // If the app is served by a frontend-only local dev/static server, the API
    // still lives on the local FastAPI backend.
    if (/^https?:\/\/(localhost|127\.0\.0\.1):(?:300\d|417\d|517\d)$/i.test(origin)) {
      return "http://127.0.0.1:8000";
    }
    return origin;
  }

  function currentApiBase() {
    return apiTargetMode === "backend" ? backendApiBase || LOCAL_API_BASE : LOCAL_API_BASE;
  }

  function apiUrl(pathOrUrl) {
    if (!pathOrUrl) return currentApiBase();
    if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
    const path = String(pathOrUrl).startsWith("/") ? String(pathOrUrl) : `/${pathOrUrl}`;
    return `${currentApiBase()}${path}`;
  }

  function apiTargetDescriptor() {
    return {
      mode: apiTargetMode,
      localApiBase: LOCAL_API_BASE,
      backendApiBase,
      apiBase: currentApiBase(),
      hasBackendApiBase: Boolean(backendApiBase),
    };
  }

  function setApiTarget(next) {
    const payload = next && typeof next === "object" ? next : {};
    const nextMode = String(payload.mode || apiTargetMode || "local").toLowerCase() === "backend" ? "backend" : "local";
    apiTargetMode = nextMode === "backend" && !backendApiBase ? "local" : nextMode;
    if (window.localStorage) {
      window.localStorage.setItem(API_MODE_STORAGE_KEY, apiTargetMode);
    }
    return apiTargetDescriptor();
  }

  const localHeaderAuthProvider = {
    id: "test_user_header",
    getActiveUserId: () => activeUserId,
    setActiveUserId: (userId) => {
      activeUserId = String(userId || "undp_analyst");
      if (window.localStorage) window.localStorage.setItem(USER_STORAGE_KEY, activeUserId);
      return activeUserId;
    },
    headers: () => ({ "X-EDIM-User-Id": activeUserId }),
  };

  let authProvider = window.EDIM_AUTH_PROVIDER || localHeaderAuthProvider;

  function currentAuthHeaders() {
    if (authProvider && typeof authProvider.headers === "function") {
      return authProvider.headers() || {};
    }
    const userId = authProvider && typeof authProvider.getActiveUserId === "function"
      ? authProvider.getActiveUserId()
      : activeUserId;
    return userId ? { "X-EDIM-User-Id": userId } : {};
  }

  function authHeaders(extra) {
    return {
      ...(extra || {}),
      ...currentAuthHeaders(),
    };
  }

  function appendQueryParam(pathOrUrl, key, value) {
    if (!value) return pathOrUrl;
    const separator = String(pathOrUrl).includes("?") ? "&" : "?";
    return `${pathOrUrl}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
  }

  function downloadUrl(pathOrUrl) {
    if (!pathOrUrl) return currentApiBase();
    const absolute = apiUrl(pathOrUrl);
    const providerId = authProvider && authProvider.id ? String(authProvider.id) : "";
    const headers = currentAuthHeaders();
    const localUserId = headers["X-EDIM-User-Id"];
    // Plain anchor downloads cannot send custom headers. The local test-user
    // auth shim also accepts user_id query params; production auth providers
    // should use cookie/session auth or fetch/blob downloads instead.
    if (providerId === "test_user_header" && localUserId) {
      return appendQueryParam(absolute, "user_id", localUserId);
    }
    return absolute;
  }

  async function parseApiError(res, defaultMessage) {
    let text = "";
    try {
      const data = await res.json();
      text = data && (data.detail || data.message || data.error) ? String(data.detail || data.message || data.error) : "";
    } catch (err) {
      try {
        text = await res.text();
      } catch (ignore) {
        text = "";
      }
    }
    if (text.trim()) return `${defaultMessage}: ${text}`;
    return `${defaultMessage}: HTTP ${res.status}`;
  }

  async function apiGet(path, defaultMessage) {
    const res = await fetch(apiUrl(path), { headers: authHeaders() });
    if (!res.ok) throw new Error(await parseApiError(res, defaultMessage));
    return res.json();
  }

  async function apiGetText(path, defaultMessage) {
    const res = await fetch(apiUrl(path), { headers: authHeaders() });
    if (!res.ok) throw new Error(await parseApiError(res, defaultMessage));
    return res.text();
  }

  async function apiPost(path, body, defaultMessage) {
    const res = await fetch(apiUrl(path), {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body == null ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await parseApiError(res, defaultMessage));
    return res.json();
  }

  async function apiPatch(path, body, defaultMessage) {
    const res = await fetch(apiUrl(path), {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body == null ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await parseApiError(res, defaultMessage));
    return res.json();
  }

  async function apiDelete(path, defaultMessage) {
    const res = await fetch(apiUrl(path), { method: "DELETE", headers: authHeaders() });
    if (!res.ok) throw new Error(await parseApiError(res, defaultMessage));
    return res.json();
  }

  async function uploadInputDataset(datasetId, file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(apiUrl(`/api/input-datasets/${encodeURIComponent(datasetId)}/upload`), {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to upload input dataset"));
    return res.json();
  }

  window.EDIM_HTTP_CLIENT = {
    API_BASE: currentApiBase(),
    getApiBase: currentApiBase,
    getApiTarget: apiTargetDescriptor,
    setApiTarget,
    parseApiError,
    apiGet,
    apiGetText,
    apiPost,
    apiPatch,
    apiDelete,
    uploadInputDataset,
    downloadUrl,
    getAuthProvider: () => authProvider,
    setAuthProvider: (provider) => {
      authProvider = provider || localHeaderAuthProvider;
    },
    getActiveUserId: () => {
      if (authProvider && typeof authProvider.getActiveUserId === "function") {
        return authProvider.getActiveUserId();
      }
      return activeUserId;
    },
    setActiveUserId: (userId) => {
      if (authProvider && typeof authProvider.setActiveUserId === "function") {
        return authProvider.setActiveUserId(userId);
      }
      return localHeaderAuthProvider.setActiveUserId(userId);
    },
  };
})();
