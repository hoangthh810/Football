const uploadState = {
  pdf: null,
  video: null
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

function wireUploadZone(zoneId, inputId, metaId, allowedLabel, validator, stateKey) {
  const zone = document.querySelector(`#${zoneId}`);
  const input = document.querySelector(`#${inputId}`);
  const meta = document.querySelector(`#${metaId}`);
  if (!zone || !input || !meta) return;

  const handleFile = (file) => {
    if (!file) return;
    if (!validator(file)) {
      meta.textContent = `Vui lòng chọn đúng file ${allowedLabel}.`;
      meta.style.color = "var(--red)";
      return;
    }

    uploadState[stateKey] = file;
    meta.style.color = "";
    meta.textContent = formatFileMeta(file);
    setUploadStatus("File đã sẵn sàng. Bấm Upload và tạo job để gửi lên backend.");
    setPipelineStep(0);
  };

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (event) => {
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

async function uploadOneFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${getApiBaseUrl()}/api/v1/upload/file`, {
    method: "POST",
    body: formData
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Upload failed with HTTP ${response.status}`);
  }

  return response.json();
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
    setUploadStatus(`Đang upload job "${jobData.job_name}" lên backend...`);
    setPipelineStep(0);

    try {
      const pdfResult = await uploadOneFile(uploadState.pdf);
      const videoResult = await uploadOneFile(uploadState.video);

      console.log("PDF upload result:", pdfResult);
      console.log("Video upload result:", videoResult);
      
      setPipelineStep(1);
      setTimeout(() => setPipelineStep(2), 450);
      setTimeout(() => setPipelineStep(3), 900);
      setUploadStatus(`Upload thành công: ${jobData.job_name}.`, "success");
      button.textContent = "Upload lại";
    } catch (error) {
      setUploadStatus(`Upload thất bại: ${error.message}`, "error");
      button.textContent = "Thử upload lại";
    } finally {
      button.disabled = false;
    }
  });
}

wireUploadZone("pdfDropZone", "pdfInput", "pdfMeta", "PDF", (file) => file.name.toLowerCase().endsWith(".pdf"), "pdf");
wireUploadZone("videoDropZone", "videoInput", "videoMeta", "video", (file) => file.type.startsWith("video/"), "video");
initUploadJobForm();
