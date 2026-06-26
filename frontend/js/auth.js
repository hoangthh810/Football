(function () {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.querySelector(".auth-orbit");
  const liveStatus = document.querySelector("[data-live-status]");
  const interactiveCards = document.querySelectorAll(".auth-card, .auth-preview");
  const inputs = document.querySelectorAll("[data-auth-input]");

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
