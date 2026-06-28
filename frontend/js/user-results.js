(function () {
if (window.__matchvisionAuthBlocked) return;

const PAGE_SIZE = 4;
const MAX_BATCH_PAGE_SCAN = 100;

const resultState = {
  batches: [],
  selectedBatchId: null,
  currentPage: 1,
  hasNextPage: false,
  analysisStarted: false,
};

const sampleDetections = [
  {
    frame: "00:12:08",
    number: "#19",
    player: "Le Quang Hai",
    team: "Hanoi FC",
    confidence: "88.9%",
  },
  {
    frame: "00:18:41",
    number: "#10",
    player: "Park Joon Ho",
    team: "Saigon United",
    confidence: "94.8%",
  },
  {
    frame: "00:31:22",
    number: "#8",
    player: "Tran Minh Khoa",
    team: "Hanoi FC",
    confidence: "91.4%",
  },
];

function getApiBaseUrl() {
  return (
    localStorage.getItem("matchvision_api_base") || "http://localhost:8000"
  ).replace(/\/$/, "");
}

function getAuthHeaders() {
  const token = localStorage.getItem("matchvision_auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function redirectIfUnauthorized(response) {
  if (!window.MatchVisionAuth?.handleUnauthorizedStatus(response.status)) return;
  throw new Error("Phiên đăng nhập đã hết hạn. Đang chuyển về trang đăng nhập.");
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
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
    dateStyle: "medium",
  }).format(date);
}

function getUploadStatusLabel(status) {
  const labels = {
    uploaded: "Đã upload",
    processing: "Đang xử lý",
    completed: "Hoàn tất",
    failed: "Lỗi",
  };

  return labels[String(status || "").toLowerCase()] || "Đã upload";
}

function getFileTypeLabel(fileType) {
  const labels = {
    video: "Video trận đấu",
    pdf: "PDF đội hình",
  };

  return labels[String(fileType || "").toLowerCase()] || "Tệp đính kèm";
}

function getFileByType(batch, fileType) {
  return batch?.files?.find((file) => file.file_type === fileType);
}

function normalizeUploadFile(rawFile) {
  return {
    ...rawFile,
    file_id: rawFile?.file_id || rawFile?._id || "",
    batch_id: rawFile?.batch_id || "",
    file_type: rawFile?.file_type || "",
    original_filename: rawFile?.original_filename || "Tệp đã upload",
    content_type: rawFile?.content_type || "",
    file_size: rawFile?.file_size,
    storage_path: rawFile?.storage_path || "",
  };
}

function groupFilesByBatch(files) {
  return files.reduce((groups, rawFile) => {
    const file = normalizeUploadFile(rawFile);
    if (!file.batch_id) return groups;

    const batchFiles = groups.get(file.batch_id) || [];
    batchFiles.push(file);
    groups.set(file.batch_id, batchFiles);
    return groups;
  }, new Map());
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
      job_note: analysisInfo.job_note || "",
    },
    files: Array.isArray(rawBatch?.files)
      ? rawBatch.files.map(normalizeUploadFile)
      : [],
    file_ids: Array.isArray(rawBatch?.file_ids) ? rawBatch.file_ids : [],
  };
}

function getBatchTitle(batch) {
  return (
    batch?.analysis_info?.job_name ||
    getFileByType(batch, "video")?.original_filename ||
    getFileByType(batch, "pdf")?.original_filename ||
    "Upload chưa đặt tên"
  );
}

function getBatchDescription(batch) {
  const info = batch?.analysis_info || {};
  const parts = [
    info.match_date ? `Ngày thi đấu: ${formatDate(info.match_date)}` : "",
    info.model_version ? `Model: ${info.model_version}` : "",
  ].filter(Boolean);

  return parts.length ? parts.join(" - ") : formatDate(batch?.created_at);
}

function getPublicFileUrl(file) {
  if (!file?.storage_path) return "";
  if (/^https?:\/\//i.test(file.storage_path)) return file.storage_path;
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
  if (Array.isArray(payload?.analysis_jobs)) {
    const filesByBatch = groupFilesByBatch(
      Array.isArray(payload?.uploads_files) ? payload.uploads_files : [],
    );

    return payload.analysis_jobs.map((job) => {
      const batchId = job?.batch_id || job?._id || job?.job_id || "";
      return normalizeBatch({
        ...job,
        files: filesByBatch.get(batchId) || job?.files || [],
      });
    });
  }
  if (Array.isArray(payload?.batches))
    return payload.batches.map(normalizeBatch);
  if (Array.isArray(payload?.jobs)) return payload.jobs.map(normalizeBatch);
  if (Array.isArray(payload?.data)) return payload.data.map(normalizeBatch);
  return [];
}

async function fetchUploadBatches(page = resultState.currentPage) {
  const skip = (page - 1) * PAGE_SIZE;
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    skip: String(skip),
  });
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/upload/analysis_jobs?${params}`,
    {
      headers: getAuthHeaders(),
    },
  );
  const payload = await response.json().catch(() => ({}));
  redirectIfUnauthorized(response);

  if (!response.ok) {
    throw new Error(
      payload.detail || `Không tải được upload. HTTP ${response.status}`,
    );
  }

  const batches = normalizeBatchResponse(payload);
  const nextParams = new URLSearchParams({
    limit: "1",
    skip: String(skip + PAGE_SIZE),
  });
  const nextResponse = await fetch(
    `${getApiBaseUrl()}/api/v1/upload/analysis_jobs?${nextParams}`,
    {
      headers: getAuthHeaders(),
    },
  );
  const nextPayload = await nextResponse.json().catch(() => ({}));
  redirectIfUnauthorized(nextResponse);

  if (!nextResponse.ok) {
    throw new Error(
      nextPayload.detail ||
        `Không kiểm tra được trang tiếp theo. HTTP ${nextResponse.status}`,
    );
  }

  return {
    batches,
    hasNextPage: normalizeBatchResponse(nextPayload).length > 0,
  };
}

async function findBatchPage(batchId, startPage = 1) {
  if (!batchId) return null;

  for (let page = startPage; page <= MAX_BATCH_PAGE_SCAN; page += 1) {
    const pageData = await fetchUploadBatches(page);
    const hasBatch = pageData.batches.some(
      (batch) => batch.batch_id === batchId,
    );

    if (hasBatch) {
      return { page, pageData };
    }

    if (!pageData.hasNextPage) return null;
  }

  return null;
}

function getPaginationPages() {
  const lastPage = resultState.hasNextPage
    ? resultState.currentPage + 1
    : resultState.currentPage;
  return Array.from({ length: lastPage }, (_, index) => index + 1);
}

function setUploadPage(page) {
  if (page < 1 || page === resultState.currentPage) return;
  loadUploadBatches({ page, shouldAutoSelect: true });
}

function renderPagination() {
  const pagination = document.querySelector("#uploadPagination");
  if (!pagination) return;

  const pages = getPaginationPages();
  pagination.hidden = resultState.currentPage === 1 && !resultState.hasNextPage;

  if (pagination.hidden) {
    pagination.innerHTML = "";
    return;
  }

  const pageButtons = pages
    .map((page) => {
      const isActive = page === resultState.currentPage;
      return `
      <button class="pagination-button${isActive ? " active" : ""}" type="button" data-page="${page}" ${isActive ? 'aria-current="page"' : ""}>
        ${page}
      </button>
    `;
    })
    .join("");

  pagination.innerHTML = `
    <button class="pagination-button pagination-step" type="button" data-page="${resultState.currentPage - 1}" ${resultState.currentPage === 1 ? "disabled" : ""}>Trước</button>
    <div class="pagination-pages" aria-label="Trang upload">
      ${pageButtons}
    </div>
    <button class="pagination-button pagination-step" type="button" data-page="${resultState.currentPage + 1}" ${!resultState.hasNextPage ? "disabled" : ""}>Sau</button>
  `;

  pagination.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      setUploadPage(Number(button.dataset.page));
    });
  });
}

function renderUploadList() {
  const list = document.querySelector("#uploadList");
  const count = document.querySelector("#uploadCount");
  if (!list || !count) return;

  count.textContent = `Trang ${resultState.currentPage}`;

  if (!resultState.batches.length) {
    list.innerHTML = `
      <div class="upload-empty">
        <strong>Chưa có dữ liệu phân tích nào</strong>
        <span>Hãy upload PDF và video ở trang Upload dữ liệu trước.</span>
      </div>
    `;
    renderPagination();
    return;
  }

  list.innerHTML = resultState.batches
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

  renderPagination();
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
    .map(
      (file) => `
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
    `,
    )
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
    videoPreview.classList.toggle("with-actions", Boolean(videoUrl));
    videoPreview.innerHTML = videoUrl
      ? `
        <video class="preview-video" src="${escapeHtml(videoUrl)}" controls preload="metadata" playsinline></video>
        <div class="media-preview-actions">
          <span>${escapeHtml(video.original_filename || "Video trận đấu")}</span>
          <a href="${escapeHtml(videoUrl)}" target="_blank" rel="noopener">Mở video</a>
        </div>
      `
      : "<span>Upload này chưa có video để preview.</span>";
  }

  if (pdfPreview) {
    const pdfUrl = getPublicFileUrl(pdf);
    pdfPreview.classList.remove("with-actions");
    pdfPreview.innerHTML = pdfUrl
      ? `<iframe title="Preview ${escapeHtml(pdf.original_filename)}" src="${escapeHtml(pdfUrl)}"></iframe>`
      : "<span>Upload này chưa có PDF để preview.</span>";
  }
}

function renderDetections(batch) {
  const body = document.querySelector("#detectionsBody");
  const resultPanel = document.querySelector("#analysisResultPanel");
  if (!body || !resultPanel) return;

  if (!resultState.analysisStarted) {
    resultPanel.hidden = true;
    return;
  }

  body.innerHTML = sampleDetections
    .map(
      (detection) => `
      <tr>
        <td>${escapeHtml(detection.frame)}</td>
        <td>${escapeHtml(detection.number)}</td>
        <td>${escapeHtml(detection.player)}</td>
        <td>${escapeHtml(detection.team)}</td>
        <td>${escapeHtml(detection.confidence)}</td>
      </tr>
    `,
    )
    .join("");

  resultPanel.hidden = false;
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

async function loadUploadBatches(options = {}) {
  const page = options.page || resultState.currentPage;
  const shouldAutoSelect = options.shouldAutoSelect !== false;
  resultState.currentPage = Math.max(1, page);
  setUploadListStatus("Đang tải danh sách upload...");

  try {
    const requestedBatchId = new URLSearchParams(window.location.search).get(
      "batch_id",
    );
    let pageData = await fetchUploadBatches(resultState.currentPage);
    const requestedBatchExistsOnPage = pageData.batches.some(
      (batch) => batch.batch_id === requestedBatchId,
    );

    if (
      resultState.currentPage === 1 &&
      requestedBatchId &&
      !requestedBatchExistsOnPage &&
      pageData.hasNextPage
    ) {
      const resolvedPage = await findBatchPage(requestedBatchId, 2);
      if (resolvedPage) {
        resultState.currentPage = resolvedPage.page;
        pageData = resolvedPage.pageData;
      }
    }

    resultState.batches = pageData.batches;
    resultState.hasNextPage = pageData.hasNextPage;

    if (!resultState.batches.length && resultState.currentPage > 1) {
      return loadUploadBatches({
        page: resultState.currentPage - 1,
        shouldAutoSelect,
      });
    }

    const hasSelectedBatch = resultState.batches.some(
      (batch) => batch.batch_id === resultState.selectedBatchId,
    );
    if (!hasSelectedBatch) {
      resultState.selectedBatchId = null;
    }

    renderUploadList();
    setUploadListStatus(
      resultState.batches.length
        ? `Trang ${resultState.currentPage}: hiển thị tối đa ${PAGE_SIZE} lượt upload.`
        : "Chưa có dữ liệu phân tích.",
    );

    const requestedBatchExists = resultState.batches.some(
      (batch) => batch.batch_id === requestedBatchId,
    );
    const firstBatchId = shouldAutoSelect
      ? requestedBatchExists
        ? requestedBatchId
        : resultState.selectedBatchId || resultState.batches[0]?.batch_id
      : null;
    if (firstBatchId) {
      selectBatch(firstBatchId);
    } else {
      resetSelectedUploadView();
    }
  } catch (error) {
    resultState.batches = [];
    resultState.currentPage = 1;
    resultState.hasNextPage = false;
    renderUploadList();
    resetSelectedUploadView();
    setUploadListStatus(getFriendlyErrorMessage(error), "error");
  }
}

function initRunAnalysisButton() {
  const button = document.querySelector("#runAnalysisButton");
  if (!button) return;

  button.addEventListener("click", () => {
    const batch = resultState.batches.find(
      (item) => item.batch_id === resultState.selectedBatchId,
    );
    if (!batch) return;

    resultState.analysisStarted = true;
    button.textContent = "Chạy lại phân tích";
    renderDetections(batch);
  });
}

document
  .querySelector("#refreshUploadsButton")
  ?.addEventListener("click", loadUploadBatches);
initRunAnalysisButton();
loadUploadBatches();

})();
