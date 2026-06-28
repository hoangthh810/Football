(function () {
  const TOKEN_KEY = "matchvision_auth_token";
  const USER_KEY = "matchvision_auth_user";
  const loginUrl = "login.html";

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getSessionUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch {
      return null;
    }
  }

  function decodeJwtPayload(token) {
    try {
      const payload = token.split(".")[1];
      if (!payload) return null;
      const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
      const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
      return JSON.parse(atob(padded));
    } catch {
      return null;
    }
  }

  function isExpired(token) {
    const payload = decodeJwtPayload(token);
    if (!payload?.exp) return false;
    return payload.exp * 1000 <= Date.now();
  }

  function redirectToLogin() {
    window.__matchvisionAuthBlocked = true;
    const currentPage = `${window.location.pathname.split("/").pop()}${window.location.search}`;
    window.location.replace(`${loginUrl}?next=${encodeURIComponent(currentPage)}`);
  }

  function handleUnauthorizedStatus(statusCode) {
    if (statusCode !== 401 && statusCode !== 403) return false;
    clearSession();
    redirectToLogin();
    return true;
  }

  function hasValidSession() {
    const token = localStorage.getItem(TOKEN_KEY);
    const user = getSessionUser();
    return Boolean(token && user && !isExpired(token));
  }

  function protectPage() {
    const requiredRole = document.body.dataset.protectedRole || "user";
    const token = localStorage.getItem(TOKEN_KEY);
    const user = getSessionUser();

    if (!token || !user || isExpired(token)) {
      clearSession();
      redirectToLogin();
      return;
    }

    if (requiredRole === "admin" && user.user_role !== "admin") {
      window.__matchvisionAuthBlocked = true;
      window.location.replace("user-upload.html");
      return;
    }

    window.__matchvisionAuthBlocked = false;
    document.documentElement.dataset.authReady = "true";
  }

  window.MatchVisionAuth = {
    clearSession,
    handleUnauthorizedStatus,
    hasValidSession,
    redirectToLogin,
  };

  document.addEventListener("click", (event) => {
    const logoutLink = event.target.closest('a[href="login.html"]');
    if (!logoutLink) return;
    clearSession();
  });

  protectPage();
  window.addEventListener("focus", protectPage);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) protectPage();
  });
  window.setInterval(protectPage, 30000);
})();
