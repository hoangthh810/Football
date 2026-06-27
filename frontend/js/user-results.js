const PAGE_SIZE = 10;

const resultState = {
  batches: [],
  selectedBatchId: null,
  visibleCount: PAGE_SIZE,
  analysisStarted: false
};

const sampleDetections = [
  { frame: "00:12:08", number: "#19", player: "Le Quang Hai", team: "Hanoi FC", confidence: "88.9%" },
  { frame: "00:18:41", number: "#10", player: "Park Joon Ho", team: "Saigon United", confidence: "94.8%" },
  { frame: "00:31:22", number: "#8", player: "Tran Minh Khoa", team: "Hanoi FC", confidence: "91.4%" }
];

function getApiBaseUrl() {
  return (localStorage.getItem("matchvision_api_base") || "http://localhost:8000").replace(/\/$/, "");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "N/A";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(value) {
  if (!value) return "Không rõ ngày";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium"
  }).format(date);
}

function getUploadStatusLabel(status) {
  const labels = {
    uploaded: "Đã upload",
    processing: "Đang xử lý",
    completed: "Hoàn tất",
    failed: "Lỗi"
  };

  return labels[String(status || "").toLowerCase()] || "Đã upload";
}

function getFileTypeLabel(fileType) {
  const labels = {
    video: "Video trận đấu",
    pdf: "PDF đội hình"
  };

  return labels[String(fileType || "").toLowerCase()] || "Tệp đính kèm";
}

function getFileByType(batch, fileType) {
  return batch?.files?.find((file) => file.file_type === fileType);
}

function normalizeBatch(rawBatch) {
  const analysisInfo = rawBatch?.analysis_info || {};
  const batchId = rawBatch?.batch_id || rawBatch?._id || rawBatch?.job_id || "";

  return {
    ...rawBatch,
    job_id: rawBatch?.job_id || rawBatch?._id || "",
    batch_id: batchId,
    analysis_info: {
      job_name: analysisInfo.job_name || "Upload chưa đặt tên",
      match_date: analysisInfo.match_date || "",
      model_version: analysisInfo.model_version || "",
      job_note: analysisInfo.job_note || ""
    },
    files: Array.isArray(rawBatch?.files) ? rawBatch.files : [],
    file_ids: Array.isArray(rawBatch?.file_ids) ? rawBatch.file_ids : []
  };
}

function getBatchTitle(batch) {
  return batch?.analysis_info?.job_name || getFileByType(batch, "video")?.original_filename || getFileByType(batch, "pdf")?.original_filename || "Upload chưa đặt tên";
}

function getBatchDescription(batch) {
  const info = batch?.analysis_info || {};
  const parts = [
    info.match_date ? `Ngày thi đấu: ${formatDate(info.match_date)}` : "",
    info.model_version ? `Model: ${info.model_version}` : ""
  ].filter(Boolean);

  return parts.length ? parts.join(" - ") : formatDate(batch?.created_at);
}

function getPublicFileUrl(file) {
  if (!file?.storage_path) return "";
  return `${getApiBaseUrl()}/${file.storage_path.replace(/^\/+/, "")}`;
}

function setUploadListStatus(message, type = "default") {
  const status = document.querySelector("#uploadListStatus");
  if (!status) return;
  status.textContent = message;
  status.style.color = type === "error" ? "var(--red)" : "";
}

function getFriendlyErrorMessage(error) {
  if (error instanceof TypeError || error.message === "Failed to fetch") {
    return "Không kết nối được máy chủ. Hãy kiểm tra backend rồi bấm Tải lại.";
  }

  return error.message || "Không tải được danh sách upload.";
}

function resetSelectedUploadView() {
  resultState.selectedBatchId = null;
  resultState.analysisStarted = false;

  const emptyState = document.querySelector("#emptyState");
  const selectedPanel = document.querySelector("#selectedUploadPanel");
  const analysisPanels = document.querySelector("#analysisPanels");
  const resultPanel = document.querySelector("#analysisResultPanel");
  const runButton = document.querySelector("#runAnalysisButton");

  if (emptyState) emptyState.hidden = false;
  if (selectedPanel) selectedPanel.hidden = true;
  if (analysisPanels) analysisPanels.hidden = true;
  if (resultPanel) resultPanel.hidden = true;
  if (runButton) runButton.textContent = "Chạy phân tích";
}

function normalizeBatchResponse(payload) {
  if (Array.isArray(payload)) return payload.map(normalizeBatch);
  if (Array.isArray(payload?.batches)) return payload.batches.map(normalizeBatch);
  if (Array.isArray(payload?.jobs)) return payload.jobs.map(normalizeBatch);
  if (Array.isArray(payload?.data)) return payload.data.map(normalizeBatch);
  return [];
}

async function fetchUploadBatches() {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/upload/analysis_jobs`);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || `Không tải được upload. HTTP ${response.status}`);
  }

  return normalizeBatchResponse(payload);
}

function renderLoadMoreButton() {
  const button = document.querySelector("#loadMoreUploadsButton");
  if (!button) return;

  const remainingCount = Math.max(0, resultState.batches.length - resultState.visibleCount);
  button.hidden = remainingCount === 0;
  button.textContent = remainingCount > PAGE_SIZE
    ? `Xem thêm ${PAGE_SIZE} lượt upload`
    : `Xem thêm ${remainingCount} lượt upload`;
}

function renderUploadList() {
  const list = document.querySelector("#uploadList");
  const count = document.querySelector("#uploadCount");
  if (!list || !count) return;

  count.textContent = `${resultState.batches.length} lượt upload`;

  if (!resultState.batches.length) {
    list.innerHTML = `
      <div class="upload-empty">
        <strong>Chưa có dữ liệu phân tích nào</strong>
        <span>Hãy upload PDF và video ở trang Upload dữ liệu trước.</span>
      </div>
    `;
    renderLoadMoreButton();
    return;
  }

  const visibleBatches = resultState.batches.slice(0, resultState.visibleCount);

  list.innerHTML = visibleBatches
    .map((batch) => {
      const info = batch.analysis_info || {};
      const isActive = batch.batch_id === resultState.selectedBatchId;
      return `
        <button class="upload-item${isActive ? " active" : ""}" type="button" data-batch-id="${escapeHtml(batch.batch_id)}">
          <span class="upload-item-top">
            <strong>${escapeHtml(info.job_name || "Upload chưa đặt tên")}</strong>
            <span class="badge done">${escapeHtml(getUploadStatusLabel(batch.status))}</span>
          </span>
          <span class="job-field">Ngày thi đấu: ${escapeHtml(info.match_date ? formatDate(info.match_date) : "Chưa có")}</span>
          <span class="job-note">Ghi chú: ${escapeHtml(info.job_note || "Không có ghi chú")}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".upload-item").forEach((button) => {
    button.addEventListener("click", () => selectBatch(button.dataset.batchId));
  });

  renderLoadMoreButton();
}

function renderSelectedFiles(batch) {
  const container = document.querySelector("#selectedFiles");
  if (!container) return;

  const info = batch.analysis_info || {};
  const jobInfoCard = `
    <article class="selected-file-card analysis-info-card">
      <div>
        <span class="badge done">Thông tin trận đấu</span>
        <h3>${escapeHtml(info.job_name || "Upload chưa đặt tên")}</h3>
      </div>
      <dl>
        <div><dt>Tên trận đấu</dt><dd>${escapeHtml(info.job_name || "Upload chưa đặt tên")}</dd></div>
        <div><dt>Ngày thi đấu</dt><dd>${escapeHtml(info.match_date ? formatDate(info.match_date) : "Chưa có")}</dd></div>
        <div><dt>Phiên bản model</dt><dd>${escapeHtml(info.model_version || "Chưa có")}</dd></div>
        <div><dt>Ghi chú</dt><dd>${escapeHtml(info.job_note || "Không có ghi chú")}</dd></div>
      </dl>
    </article>
  `;

  const fileCards = (batch.files || [])
    .map((file) => `
      <article class="selected-file-card">
        <div>
          <span class="badge ${file.file_type === "video" ? "running" : "done"}">${escapeHtml(getFileTypeLabel(file.file_type))}</span>
          <h3>${escapeHtml(file.original_filename || "Tệp đã upload")}</h3>
        </div>
        <dl>
          <div><dt>Dung lượng</dt><dd>${formatBytes(file.file_size)}</dd></div>
          <div><dt>Định dạng</dt><dd>${escapeHtml(file.content_type || "Chưa rõ")}</dd></div>
        </dl>
      </article>
    `)
    .join("");

  container.innerHTML = jobInfoCard + fileCards;
}

function renderPreviews(batch) {
  const analysisPanels = document.querySelector("#analysisPanels");
  const videoPreview = document.querySelector("#videoPreview");
  const pdfPreview = document.querySelector("#pdfPreview");
  const video = getFileByType(batch, "video");
  const pdf = getFileByType(batch, "pdf");
  const hasPreviewFiles = Boolean(video || pdf);

  if (analysisPanels) analysisPanels.hidden = !hasPreviewFiles;

  if (videoPreview) {
    const videoUrl = getPublicFileUrl(video);
    videoPreview.innerHTML = videoUrl
      ? `<video src="${escapeHtml(videoUrl)}" controls preload="metadata"></video>`
      : "<span>Upload này chưa có video để preview.</span>";
  }

  if (pdfPreview) {
    const pdfUrl = getPublicFileUrl(pdf);
    pdfPreview.innerHTML = pdfUrl
      ? `<iframe title="Preview ${escapeHtml(pdf.original_filename)}" src="${escapeHtml(pdfUrl)}"></iframe>`
      : "<span>Upload này chưa có PDF để preview.</span>";
  }
}

function renderDetections(batch) {
  const body = document.querySelector("#detectionsBody");
  const resultPanel = document.querySelector("#analysisResultPanel");
  const selectedPlayer = document.querySelector("#selectedPlayer");
  if (!body || !resultPanel) return;

  if (!resultState.analysisStarted) {
    resultPanel.hidden = true;
    if (selectedPlayer) {
      selectedPlayer.innerHTML = `<span class="status-dot"></span>Chạy phân tích để xem mapping cầu thủ.`;
    }
    return;
  }

  body.innerHTML = sampleDetections
    .map((detection) => `
      <tr>
        <td>${escapeHtml(detection.frame)}</td>
        <td>${escapeHtml(detection.number)}</td>
        <td>${escapeHtml(detection.player)}</td>
        <td>${escapeHtml(detection.team)}</td>
        <td>${escapeHtml(detection.confidence)}</td>
      </tr>
    `)
    .join("");

  resultPanel.hidden = false;
  if (selectedPlayer) {
    selectedPlayer.innerHTML = `
      <span class="status-dot"></span>
      <span>
        Đã chạy phân tích cho <strong>${escapeHtml(getBatchTitle(batch))}</strong>.
        Kết quả hiện là dữ liệu demo cho tới khi backend inference được nối vào.
      </span>
    `;
  }
}

function selectBatch(batchId) {
  const batch = resultState.batches.find((item) => item.batch_id === batchId);
  if (!batch) return;

  resultState.selectedBatchId = batchId;
  resultState.analysisStarted = false;

  const emptyState = document.querySelector("#emptyState");
  const selectedPanel = document.querySelector("#selectedUploadPanel");
  const title = document.querySelector("#selectedBatchTitle");
  const meta = document.querySelector("#selectedBatchMeta");
  const runButton = document.querySelector("#runAnalysisButton");

  if (emptyState) emptyState.hidden = true;
  if (selectedPanel) selectedPanel.hidden = false;
  if (title) title.textContent = getBatchTitle(batch);
  if (meta) meta.textContent = getBatchDescription(batch);
  if (runButton) runButton.textContent = "Chạy phân tích";

  renderUploadList();
  renderSelectedFiles(batch);
  renderPreviews(batch);
  renderDetections(batch);
}

async function loadUploadBatches() {
  setUploadListStatus("Đang tải danh sách upload...");

  try {
    resultState.batches = await fetchUploadBatches();
    resultState.visibleCount = PAGE_SIZE;
    const hasSelectedBatch = resultState.batches.some((batch) => batch.batch_id === resultState.selectedBatchId);
    if (!hasSelectedBatch) {
      resultState.selectedBatchId = null;
    }

    renderUploadList();
    setUploadListStatus(resultState.batches.length ? "Mỗi lần hiển thị 10 lượt upload. Bấm Xem thêm để tải tiếp." : "Chưa có dữ liệu phân tích.");

    const requestedBatchId = new URLSearchParams(window.location.search).get("batch_id");
    const requestedBatchExists = resultState.batches.some((batch) => batch.batch_id === requestedBatchId);
    const firstBatchId = requestedBatchExists ? requestedBatchId : resultState.selectedBatchId || resultState.batches[0]?.batch_id;
    if (firstBatchId) {
      selectBatch(firstBatchId);
    } else {
      resetSelectedUploadView();
    }
  } catch (error) {
    resultState.batches = [];
    resultState.visibleCount = PAGE_SIZE;
    renderUploadList();
    resetSelectedUploadView();
    setUploadListStatus(getFriendlyErrorMessage(error), "error");
  }
}

function initRunAnalysisButton() {
  const button = document.querySelector("#runAnalysisButton");
  if (!button) return;

  button.addEventListener("click", () => {
    const batch = resultState.batches.find((item) => item.batch_id === resultState.selectedBatchId);
    if (!batch) return;

    resultState.analysisStarted = true;
    button.textContent = "Chạy lại phân tích";
    renderDetections(batch);
  });
}

function initLoadMoreButton() {
  const button = document.querySelector("#loadMoreUploadsButton");
  if (!button) return;

  button.addEventListener("click", () => {
    resultState.visibleCount += PAGE_SIZE;
    renderUploadList();
  });
}

document.querySelector("#refreshUploadsButton")?.addEventListener("click", loadUploadBatches);
initRunAnalysisButton();
initLoadMoreButton();
loadUploadBatches();
