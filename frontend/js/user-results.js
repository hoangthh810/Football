const sampleLineups = {
  home: [
    { number: 1, name: "Nguyen Van Lam", position: "GK" },
    { number: 4, name: "Do Thanh Binh", position: "CB" },
    { number: 8, name: "Tran Minh Khoa", position: "CM" },
    { number: 11, name: "Hoang Bao Long", position: "LW" },
    { number: 19, name: "Le Quang Hai", position: "ST" }
  ],
  away: [
    { number: 3, name: "Kim Min Su", position: "CB" },
    { number: 7, name: "Pham Duc Anh", position: "RW" },
    { number: 10, name: "Park Joon Ho", position: "AM" },
    { number: 16, name: "Vo Nhat Nam", position: "DM" },
    { number: 22, name: "Bui Anh Tuan", position: "GK" }
  ]
};

const playerProfiles = {
  "Nguyen Van Lam": { team: "Hanoi FC", number: 1, confidence: "96.2%", role: "Goalkeeper" },
  "Tran Minh Khoa": { team: "Hanoi FC", number: 8, confidence: "91.4%", role: "Central midfielder" },
  "Le Quang Hai": { team: "Hanoi FC", number: 19, confidence: "88.9%", role: "Striker" },
  "Park Joon Ho": { team: "Saigon United", number: 10, confidence: "94.8%", role: "Attacking midfielder" },
  "Pham Duc Anh": { team: "Saigon United", number: 7, confidence: "89.7%", role: "Right winger" }
};

function renderLineup(teamKey) {
  const lineupBody = document.querySelector("#lineupBody");
  if (!lineupBody) return;

  lineupBody.innerHTML = sampleLineups[teamKey]
    .map((player) => `
      <tr>
        <td>#${player.number}</td>
        <td>${player.name}</td>
        <td>${player.position}</td>
      </tr>
    `)
    .join("");
}

function initTabs() {
  const tabs = Array.from(document.querySelectorAll(".tab"));
  if (!tabs.length) return;

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      renderLineup(tab.dataset.team);
    });
  });

  renderLineup("home");
}

function initPlayerBoxes() {
  const selectedPlayer = document.querySelector("#selectedPlayer");
  if (!selectedPlayer) return;

  document.querySelectorAll(".player-box").forEach((box) => {
    box.addEventListener("click", () => {
      const name = box.dataset.player;
      const profile = playerProfiles[name];
      if (!profile) return;

      selectedPlayer.innerHTML = `
        <span class="status-dot"></span>
        <span>
          <strong>#${profile.number} ${name}</strong> - ${profile.team}, ${profile.role}.
          Match confidence: ${profile.confidence}
        </span>
      `;
    });
  });
}

initTabs();
initPlayerBoxes();
