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

  class ApiRequestError extends Error {
    constructor(message, details) {
      super(message);
      this.name = "ApiRequestError";
      Object.assign(this, details || {});
    }
  }

  function requestId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `edim-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function wait(delayMs) {
    return new Promise((resolve) => window.setTimeout(resolve, delayMs));
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

  function responseErrorMessage(status, detail, defaultMessage) {
    const suffix = detail ? ` ${detail}` : "";
    if (status === 401 || status === 403) {
      return `Your session is not authorized for this action.${suffix}`;
    }
    if (status === 409) {
      return `${defaultMessage}.${suffix || " The resource changed or requires acknowledgement."}`;
    }
    if (status === 422) {
      return `The backend could not validate this request.${suffix}`;
    }
    if (status >= 500) {
      return `The modeling service encountered an error while processing this request.${suffix}`;
    }
    return `${defaultMessage}.${suffix || ` HTTP ${status}.`}`;
  }

  async function request(path, options) {
    const config = options || {};
    const method = String(config.method || "GET").toUpperCase();
    const safeRead = method === "GET";
    const attempts = safeRead ? 3 : 1;
    const timeoutMs = Number(config.timeoutMs) || 20000;
    const url = apiUrl(path);
    const correlationId = requestId();

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(url, {
          method,
          headers: authHeaders({
            ...(config.headers || {}),
            "X-Request-Id": correlationId,
          }),
          body: config.body,
          signal: controller.signal,
        });
        if (!response.ok) {
          const parsed = await parseApiError(response, config.defaultMessage || "Request failed");
          const detail = parsed.includes(": ") ? parsed.split(": ").slice(1).join(": ") : parsed;
          const retryable = safeRead && [502, 503, 504].includes(response.status) && attempt < attempts;
          if (retryable) {
            await wait(250 * attempt);
            continue;
          }
          throw new ApiRequestError(
            responseErrorMessage(response.status, detail, config.defaultMessage || "Request failed"),
            {
              kind: response.status === 401 || response.status === 403
                ? "authorization"
                : response.status === 422
                  ? "validation"
                  : response.status >= 500
                    ? "backend"
                    : "request",
              status: response.status,
              requestId: response.headers.get("X-Request-Id") || correlationId,
              url,
            }
          );
        }
        return config.responseType === "text" ? response.text() : response.json();
      } catch (error) {
        if (error instanceof ApiRequestError) throw error;
        const timedOut = error && error.name === "AbortError";
        const offline = typeof navigator !== "undefined" && navigator.onLine === false;
        if (safeRead && !offline && !timedOut && attempt < attempts) {
          await wait(250 * attempt);
          continue;
        }
        const message = offline
          ? "You appear to be offline. Reconnect and try again."
          : timedOut
            ? `The modeling service did not respond within ${Math.round(timeoutMs / 1000)} seconds.`
            : `Cannot reach the modeling service at ${currentApiBase()}. Check that the selected service is running and try again.`;
        throw new ApiRequestError(message, {
          kind: offline ? "offline" : timedOut ? "timeout" : "unavailable",
          requestId: correlationId,
          url,
          cause: error,
        });
      } finally {
        window.clearTimeout(timeout);
      }
    }
    throw new ApiRequestError("The modeling service is unavailable.", { kind: "unavailable", requestId: correlationId, url });
  }

  function apiGet(path, defaultMessage) {
    return request(path, { defaultMessage });
  }

  function apiGetText(path, defaultMessage) {
    return request(path, { defaultMessage, responseType: "text" });
  }

  function apiPost(path, body, defaultMessage) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body == null ? undefined : JSON.stringify(body),
      defaultMessage,
    });
  }

  function apiPatch(path, body, defaultMessage) {
    return request(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: body == null ? undefined : JSON.stringify(body),
      defaultMessage,
    });
  }

  function apiDelete(path, defaultMessage) {
    return request(path, { method: "DELETE", defaultMessage });
  }

  async function uploadInputDataset(datasetId, file) {
    const form = new FormData();
    form.append("file", file);
    return request(`/api/input-datasets/${encodeURIComponent(datasetId)}/upload`, {
      method: "POST",
      body: form,
      defaultMessage: "Failed to upload input dataset",
      timeoutMs: 120000,
    });
  }

  window.EDIM_HTTP_CLIENT = {
    API_BASE: currentApiBase(),
    getApiBase: currentApiBase,
    getApiTarget: apiTargetDescriptor,
    setApiTarget,
    ApiRequestError,
    parseApiError,
    request,
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
