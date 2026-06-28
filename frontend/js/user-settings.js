(function () {
if (window.__matchvisionAuthBlocked) return;

function initApiSettings() {
  const apiBase = document.querySelector("#apiBase");
  const apiStatus = document.querySelector("#apiStatus");
  const saveApi = document.querySelector("#saveApi");
  if (!apiBase || !apiStatus || !saveApi) return;

  const savedApi = localStorage.getItem("matchvision_api_base");
  if (savedApi) apiBase.value = savedApi;

  saveApi.addEventListener("click", () => {
    localStorage.setItem("matchvision_api_base", apiBase.value.trim());
    apiStatus.textContent = `Đã lưu endpoint: ${apiBase.value.trim()}`;
  });
}

initApiSettings();

})();
