(function () {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.querySelector(".auth-orbit");
  const liveStatus = document.querySelector("[data-live-status]");
  const interactiveCards = document.querySelectorAll(".auth-card, .auth-preview");
  const inputs = document.querySelectorAll("[data-auth-input]");
  const authForm = document.querySelector("[data-auth-form]");
  const authMessage = document.querySelector("[data-auth-message]");
  const submitButton = document.querySelector("[data-submit-button]");
  const TOKEN_KEY = "matchvision_auth_token";
  const USER_KEY = "matchvision_auth_user";

  function getApiBaseUrl() {
    return (localStorage.getItem("matchvision_api_base") || "http://localhost:8000").replace(/\/$/, "");
  }

  function setAuthMessage(message, type = "default") {
    if (!authMessage) return;
    authMessage.textContent = message;
    authMessage.dataset.state = type;
  }

  function getErrorMessage(payload, fallback) {
    if (typeof payload === "string") return payload;
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.detail) && payload.detail.length) {
      return payload.detail
        .map((item) => item?.msg || item?.message || "")
        .filter(Boolean)
        .join(" ");
    }
    if (typeof payload?.message === "string") return payload.message;
    return fallback;
  }

  async function parseResponseBody(response) {
    const text = await response.text();
    if (!text) return {};

    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  function extractToken(loginPayload) {
    if (typeof loginPayload === "string") return loginPayload;
    if (typeof loginPayload?.access_token === "string") return loginPayload.access_token;
    if (typeof loginPayload?.token === "string") return loginPayload.token;
    return "";
  }

  async function fetchProfile(token) {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/profile`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const payload = await parseResponseBody(response);

    if (!response.ok) {
      throw new Error(getErrorMessage(payload, `Không tải được hồ sơ người dùng. HTTP ${response.status}`));
    }

    return payload;
  }

  function saveSession(token, profile) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(
      USER_KEY,
      JSON.stringify({
        user_id: profile.user_id,
        user_email: profile.user_email,
        user_fullname: profile.user_fullname,
        user_role: profile.user_role,
        token_type: "bearer",
      }),
    );
  }

  function getNextUrl(userRole) {
    const requestedNext = new URLSearchParams(window.location.search).get("next");
    if (requestedNext) {
      const nextFile = requestedNext.split("?")[0];
      const isLocalPage = /^[a-z0-9-]+\.html$/i.test(nextFile);
      const isAdminTarget = nextFile.startsWith("admin-");
      if (isLocalPage && (!isAdminTarget || userRole === "admin")) return requestedNext;
    }

    return userRole === "admin" ? "admin-dashboard.html" : "user-upload.html";
  }

  function setFilledState(input) {
    input.classList.toggle("is-filled", Boolean(input.value.trim()));
  }

  inputs.forEach((input) => {
    setFilledState(input);
    input.addEventListener("input", () => setFilledState(input));
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-field")?.querySelector("[data-password-input]");
      if (!input) return;

      const nextType = input.type === "password" ? "text" : "password";
      input.type = nextType;
      button.textContent = nextType === "password" ? "Hiện" : "Ẩn";
      input.focus();
    });
  });

  if (document.body.dataset.authPage === "register" && authForm) {
    authForm.addEventListener("submit", async (event) => {
      event.preventDefault();

      const formData = new FormData(authForm);
      const payload = {
        user_fullname: String(formData.get("user_fullname") || "").trim(),
        user_email: String(formData.get("user_email") || "").trim(),
        user_role: String(formData.get("user_role") || "user"),
        user_password: String(formData.get("user_password") || ""),
      };

      setAuthMessage("Đang tạo tài khoản...", "loading");
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Đang tạo...";
      }

      try {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/register`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const result = await parseResponseBody(response);

        if (!response.ok) {
          throw new Error(getErrorMessage(result, `Đăng ký thất bại. HTTP ${response.status}`));
        }

        setAuthMessage(result.message || "Đăng ký tài khoản thành công.", "success");
        window.setTimeout(() => {
          window.location.href = "login.html";
        }, 900);
      } catch (error) {
        const isNetworkError = error instanceof TypeError || error.message === "Failed to fetch";
        setAuthMessage(
          isNetworkError
            ? "Không kết nối được máy chủ. Hãy kiểm tra backend rồi thử lại."
            : error.message,
          "error",
        );
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Tạo tài khoản";
        }
      }
    });
  }

  if (document.body.dataset.authPage === "login" && authForm) {
    authForm.addEventListener("submit", async (event) => {
      event.preventDefault();

      const formData = new FormData(authForm);
      const payload = {
        user_email: String(formData.get("user_email") || "").trim(),
        user_password: String(formData.get("user_password") || ""),
      };

      setAuthMessage("Đang đăng nhập...", "loading");
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Đang đăng nhập...";
      }

      try {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const result = await parseResponseBody(response);

        if (!response.ok) {
          throw new Error(getErrorMessage(result, `Đăng nhập thất bại. HTTP ${response.status}`));
        }

        const token = extractToken(result);
        if (!token) {
          throw new Error("Backend không trả token đăng nhập hợp lệ.");
        }

        const profile = await fetchProfile(token);
        saveSession(token, profile);
        setAuthMessage("Đăng nhập thành công.", "success");
        window.setTimeout(() => {
          window.location.href = getNextUrl(profile.user_role);
        }, 500);
      } catch (error) {
        const isNetworkError = error instanceof TypeError || error.message === "Failed to fetch";
        setAuthMessage(
          isNetworkError
            ? "Không kết nối được máy chủ. Hãy kiểm tra backend rồi thử lại."
            : error.message,
          "error",
        );
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Đăng nhập";
        }
      }
    });
  }

  if (!prefersReducedMotion && liveStatus) {
    const loginStatuses = ["Running", "Parsing PDF", "Detecting", "Mapping"];
    const registerStatuses = ["Ready", "Creating", "Syncing", "Prepared"];
    const statuses = document.body.dataset.authPage === "register" ? registerStatuses : loginStatuses;
    let index = 0;

    window.setInterval(() => {
      index = (index + 1) % statuses.length;
      liveStatus.textContent = statuses[index];
    }, 2200);
  }

  if (!prefersReducedMotion) {
    document.addEventListener("pointermove", (event) => {
      const x = event.clientX / window.innerWidth - 0.5;
      const y = event.clientY / window.innerHeight - 0.5;
      interactiveCards.forEach((card) => {
        card.style.setProperty("--tilt-x", `${(-y * 4).toFixed(2)}deg`);
        card.style.setProperty("--tilt-y", `${(x * 5).toFixed(2)}deg`);
      });
    });

    document.addEventListener("pointerleave", () => {
      interactiveCards.forEach((card) => {
        card.style.setProperty("--tilt-x", "0deg");
        card.style.setProperty("--tilt-y", "0deg");
      });
    });
  }

  if (!canvas || prefersReducedMotion) return;

  const context = canvas.getContext("2d");
  const particles = [];
  const particleCount = 54;
  let width = 0;
  let height = 0;
  let lastTime = 0;

  function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function createParticle() {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 1.8 + 0.8,
      speedX: (Math.random() - 0.5) * 18,
      speedY: (Math.random() - 0.5) * 18
    };
  }

  function seedParticles() {
    particles.length = 0;
    for (let i = 0; i < particleCount; i += 1) {
      particles.push(createParticle());
    }
  }

  function draw(timestamp) {
    const delta = Math.min((timestamp - lastTime) / 1000 || 0, 0.033);
    lastTime = timestamp;

    context.clearRect(0, 0, width, height);
    context.fillStyle = "rgba(168, 255, 95, 0.75)";
    context.strokeStyle = "rgba(53, 214, 255, 0.16)";
    context.lineWidth = 1;

    particles.forEach((particle) => {
      particle.x += particle.speedX * delta;
      particle.y += particle.speedY * delta;

      if (particle.x < -20) particle.x = width + 20;
      if (particle.x > width + 20) particle.x = -20;
      if (particle.y < -20) particle.y = height + 20;
      if (particle.y > height + 20) particle.y = -20;

      context.beginPath();
      context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
      context.fill();
    });

    for (let i = 0; i < particles.length; i += 1) {
      for (let j = i + 1; j < particles.length; j += 1) {
        const a = particles[i];
        const b = particles[j];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (distance > 150) continue;

        context.globalAlpha = 1 - distance / 150;
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();
      }
    }

    context.globalAlpha = 1;
    window.requestAnimationFrame(draw);
  }

  resizeCanvas();
  seedParticles();
  window.addEventListener("resize", () => {
    resizeCanvas();
    seedParticles();
  });
  window.requestAnimationFrame(draw);
})();
