const uploadState = {
  pdf: null,
  video: null
};

const previewUrls = {
  pdf: null,
  video: null
};

const uploadRules = {
  pdf: {
    label: "PDF",
    extensions: [".pdf"],
    contentTypes: ["application/pdf"],
    maxSizeMb: 10
  },
  video: {
    label: "MP4",
    extensions: [".mp4"],
    contentTypes: ["video/mp4"],
    maxSizeMb: 50
  }
};

function setPipelineStep(stepIndex) {
  document.querySelectorAll("#pipelineList li").forEach((item, index) => {
    item.classList.toggle("active", index <= stepIndex);
  });
}

function formatFileMeta(file) {
  return `${file.name} - ${(file.size / 1024 / 1024).toFixed(2)} MB`;
}

function getApiBaseUrl() {
  return (localStorage.getItem("matchvision_api_base") || "http://localhost:8000").replace(/\/$/, "");
}

function setUploadStatus(message, type = "default") {
  const status = document.querySelector("#uploadStatus");
  if (!status) return;

  status.textContent = message;
  status.style.color = type === "error" ? "var(--red)" : type === "success" ? "var(--green)" : "";
}

function setOverlayProgress(percent) {
  const progressBar = document.querySelector("#uploadProgressBar");
  const progressText = document.querySelector("#uploadProgressText");
  const value = Math.max(0, Math.min(100, Math.round(percent)));

  if (progressBar) progressBar.style.width = `${value}%`;
  if (progressText) progressText.textContent = `${value}%`;
}

function setUploadOverlay(state, title, message, percent = 0) {
  const overlay = document.querySelector("#uploadOverlay");
  const modal = overlay?.querySelector(".upload-modal");
  const icon = document.querySelector("#uploadOverlayIcon");
  const titleElement = document.querySelector("#uploadOverlayTitle");
  const messageElement = document.querySelector("#uploadOverlayMessage");
  const closeButton = document.querySelector("#uploadOverlayClose");
  if (!overlay || !modal || !icon || !titleElement || !messageElement || !closeButton) return;

  overlay.hidden = false;
  modal.classList.remove("uploading", "success", "error");
  modal.classList.add(state);
  icon.textContent = state === "success" ? "OK" : state === "error" ? "!" : "...";
  titleElement.textContent = title;
  messageElement.textContent = message;
  closeButton.hidden = state === "uploading";
  setOverlayProgress(percent);
}

function closeUploadOverlay() {
  const overlay = document.querySelector("#uploadOverlay");
  if (overlay) overlay.hidden = true;
}

function getFileExtension(fileName) {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toLowerCase() : "";
}

function validateSelectedFile(file, rule) {
  const extension = getFileExtension(file.name);
  const hasValidExtension = rule.extensions.includes(extension);
  const hasValidContentType = !file.type || rule.contentTypes.includes(file.type);
  const maxSizeBytes = rule.maxSizeMb * 1024 * 1024;

  if (!hasValidExtension || !hasValidContentType) {
    return `Vui lòng chọn đúng file ${rule.label}. Backend hiện chỉ nhận ${rule.extensions.join(", ")}.`;
  }

  if (file.size > maxSizeBytes) {
    return `File quá lớn. Tối đa ${rule.maxSizeMb}MB cho ${rule.label}.`;
  }

  return "";
}

function resetUploadResult() {
  const panel = document.querySelector("#uploadResultPanel");
  const container = document.querySelector("#uploadedFiles");
  if (panel) panel.hidden = true;
  if (container) container.innerHTML = "";
}

function clearFilePreview(stateKey) {
  const preview = document.querySelector(`#${stateKey}Preview`);
  const zone = document.querySelector(`#${stateKey}DropZone`);

  if (previewUrls[stateKey]) {
    URL.revokeObjectURL(previewUrls[stateKey]);
    previewUrls[stateKey] = null;
  }

  if (preview) {
    preview.innerHTML = "";
    preview.hidden = true;
  }

  if (zone) zone.classList.remove("has-file");
}

function renderFilePreview(stateKey, file) {
  const preview = document.querySelector(`#${stateKey}Preview`);
  const zone = document.querySelector(`#${stateKey}DropZone`);
  if (!preview) return;

  clearFilePreview(stateKey);

  const objectUrl = URL.createObjectURL(file);
  previewUrls[stateKey] = objectUrl;
  preview.hidden = false;
  if (zone) zone.classList.add("has-file");

  if (stateKey === "pdf") {
    preview.innerHTML = `<iframe title="Preview ${escapeHtml(file.name)}" src="${objectUrl}"></iframe>`;
    return;
  }

  preview.innerHTML = `<video src="${objectUrl}" controls preload="metadata"></video>`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "N/A";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
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

function renderUploadResults(results) {
  const panel = document.querySelector("#uploadResultPanel");
  const container = document.querySelector("#uploadedFiles");
  if (!panel || !container) return;

  container.innerHTML = results
    .map((result) => `
      <article class="uploaded-file-card">
        <div>
          <span class="badge done">${escapeHtml(result.file_type || "uploaded")}</span>
          <h3>${escapeHtml(result.original_filename || "Uploaded file")}</h3>
        </div>
        <dl>
          <div><dt>File ID</dt><dd>${escapeHtml(result.file_id || "N/A")}</dd></div>
          <div><dt>Dung lượng</dt><dd>${formatBytes(result.file_size)}</dd></div>
          <div><dt>Content type</dt><dd>${escapeHtml(result.content_type || "N/A")}</dd></div>
          <div><dt>Storage path</dt><dd>${escapeHtml(result.storage_path || "N/A")}</dd></div>
        </dl>
      </article>
    `)
    .join("");

  panel.hidden = false;
}

function getErrorMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg || JSON.stringify(item)).join(", ");
  return fallback;
}

function wireUploadZone(zoneId, inputId, metaId, stateKey) {
  const zone = document.querySelector(`#${zoneId}`);
  const input = document.querySelector(`#${inputId}`);
  const meta = document.querySelector(`#${metaId}`);
  const browseButton = zone?.querySelector(".file-button");
  const rule = uploadRules[stateKey];
  if (!zone || !input || !meta) return;

  const handleFile = (file) => {
    if (!file) return;
    const validationMessage = validateSelectedFile(file, rule);
    if (validationMessage) {
      uploadState[stateKey] = null;
      clearFilePreview(stateKey);
      meta.textContent = validationMessage;
      meta.style.color = "var(--red)";
      setUploadStatus(validationMessage, "error");
      return;
    }

    uploadState[stateKey] = file;
    meta.style.color = "";
    meta.textContent = formatFileMeta(file);
    renderFilePreview(stateKey, file);
    setUploadStatus("File đã sẵn sàng. Bấm Upload và tạo job để gửi lên backend.");
    setPipelineStep(0);
    resetUploadResult();
  };

  browseButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    input.click();
  });

  zone.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest(".file-preview")) return;
    if (event.target instanceof Element && event.target.closest(".file-button")) return;
    input.click();
  });
  zone.addEventListener("keydown", (event) => {
    if (event.target instanceof Element && event.target.closest(".file-preview")) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", (event) => handleFile(event.target.files[0]));

  ["dragenter", "dragover"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.remove("dragging");
    });
  });

  zone.addEventListener("drop", (event) => handleFile(event.dataTransfer.files[0]));
}

function parseUploadResponse(request) {
  const contentType = request.getResponseHeader("content-type") || "";

  if (!contentType.includes("application/json")) {
    return request.responseText;
  }

  try {
    return JSON.parse(request.responseText || "{}");
  } catch {
    return request.responseText;
  }
}

function uploadMatchFiles(pdfFile, videoFile, jobData, onProgress) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("pdf_file", pdfFile);
    formData.append("video_file", videoFile);
    formData.append("job_name", jobData.job_name);
    formData.append("match_date", jobData.match_date);
    formData.append("model_version", jobData.model_version);
    formData.append("job_note", jobData.job_note || "");

    const request = new XMLHttpRequest();
    request.open("POST", `${getApiBaseUrl()}/api/v1/upload/match-files`);

    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const percent = (event.loaded / event.total) * 100;
      onProgress(percent);
    });

    request.addEventListener("load", () => {
      const payload = parseUploadResponse(request);

      if (request.status >= 200 && request.status < 300) {
        resolve(payload);
        return;
      }

      reject(new Error(getErrorMessage(payload, `Upload failed with HTTP ${request.status}`)));
    });

    request.addEventListener("error", () => {
      reject(new Error("Không kết nối được backend. Vui lòng kiểm tra server hoặc mạng."));
    });

    request.addEventListener("abort", () => {
      reject(new Error("Upload đã bị hủy."));
    });

    request.send(formData);
  });
}

function initUploadJobForm() {
  const form = document.querySelector("#uploadJobForm");
  const button = document.querySelector("#uploadJobButton");
  if (!form || !button) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const jobData = Object.fromEntries(new FormData(form).entries());
    if (!uploadState.pdf || !uploadState.video) {
      setUploadStatus("Vui lòng chọn đủ PDF và video trước khi upload.", "error");
      return;
    }

    button.disabled = true;
    button.textContent = "Đang upload...";
    resetUploadResult();
    setUploadStatus(`Đang upload PDF và video cho job "${jobData.job_name}"...`);
    setUploadOverlay("uploading", "Đang upload", "Đang gửi PDF và video lên backend.", 0);
    setPipelineStep(0);

    try {
      const uploadResult = await uploadMatchFiles(uploadState.pdf, uploadState.video, jobData, (percent) => {
        setOverlayProgress(percent);
        if (percent >= 100) {
          setUploadOverlay("uploading", "Đang xử lý", "File đã gửi xong. Đang chờ backend lưu dữ liệu.", 100);
        }
      });
      const uploadedFiles = Array.isArray(uploadResult.files) ? uploadResult.files : [];

      renderUploadResults(uploadedFiles);
      setPipelineStep(1);
      setTimeout(() => setPipelineStep(2), 450);
      setTimeout(() => setPipelineStep(3), 900);
      setUploadStatus(`Upload thành công: ${jobData.job_name}. Job ${uploadResult.job_id || "N/A"} đã lưu thông tin phân tích và batch ${uploadResult.batch_id}.`, "success");
      setUploadOverlay("success", "Upload thành công", `Backend đã lưu job phân tích ${uploadResult.job_id || "N/A"} cho batch ${uploadResult.batch_id}.`, 100);
      button.textContent = "Upload lại";
    } catch (error) {
      setUploadStatus(`Upload thất bại: ${error.message}`, "error");
      setUploadOverlay("error", "Upload thất bại", error.message, 100);
      button.textContent = "Thử upload lại";
    } finally {
      button.disabled = false;
    }
  });
}

wireUploadZone("pdfDropZone", "pdfInput", "pdfMeta", "pdf");
wireUploadZone("videoDropZone", "videoInput", "videoMeta", "video");
document.querySelector("#uploadOverlayClose")?.addEventListener("click", closeUploadOverlay);
initUploadJobForm();
