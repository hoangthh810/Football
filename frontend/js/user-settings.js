(function () {
if (window.__matchvisionAuthBlocked) return;

const TOKEN_KEY = "matchvision_auth_token";
const USER_KEY = "matchvision_auth_user";

function getApiBaseUrl() {
  return (localStorage.getItem("matchvision_api_base") || "http://localhost:8000").replace(/\/$/, "");
}

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

function getRoleLabel(role) {
  return role === "admin" ? "Admin" : "Người dùng";
}

function getInitials(nameOrEmail) {
  const value = String(nameOrEmail || "MV").trim();
  const words = value.includes("@") ? value.split("@")[0].split(/[._-]+/) : value.split(/\s+/);
  return words
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("") || "MV";
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function renderProfile(profile, statusMessage = "Đã đồng bộ hồ sơ từ backend.") {
  const fullname = profile?.user_fullname || "Chưa có tên";
  const email = profile?.user_email || "Chưa có email";
  const roleLabel = getRoleLabel(profile?.user_role);

  setText("#profileAvatar", getInitials(fullname || email));
  setText("#profileName", fullname);
  setText("#profileEmail", email);
  setText("#profileRole", roleLabel);
  setText("#profileFullname", fullname);
  setText("#profileEmailField", email);
  setText("#profileRoleField", roleLabel);
  setText("#profileStatus", statusMessage);
}

async function fetchProfile() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) throw new Error("Không tìm thấy token đăng nhập.");

  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/profile`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  const payload = await response.json().catch(() => ({}));

  if (response.status === 401 || response.status === 403) {
    window.MatchVisionAuth?.handleUnauthorizedStatus(response.status);
    return null;
  }

  if (!response.ok) {
    throw new Error(payload.detail || `Không tải được hồ sơ. HTTP ${response.status}`);
  }

  return payload;
}

async function initProfileSettings() {
  const storedUser = getStoredUser();
  if (storedUser) {
    renderProfile(storedUser, "Đang kiểm tra lại hồ sơ với backend.");
  }

  try {
    const profile = await fetchProfile();
    if (!profile) return;
    localStorage.setItem(
      USER_KEY,
      JSON.stringify({
        ...storedUser,
        ...profile,
        token_type: storedUser?.token_type || "bearer",
      }),
    );
    renderProfile(profile);
  } catch (error) {
    if (storedUser) {
      renderProfile(storedUser, error.message);
      return;
    }

    setText("#profileName", "Không tải được hồ sơ");
    setText("#profileEmail", "Hãy đăng nhập lại để đồng bộ tài khoản.");
    setText("#profileStatus", error.message);
  }
}

initProfileSettings();

})();
