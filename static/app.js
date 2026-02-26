const statusNode = document.getElementById("status");
const galleryNode = document.getElementById("gallery");
const saveDirInput = document.getElementById("save-dir");
const hotkeyInput = document.getElementById("hotkey");

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.style.color = isError ? "#bd2f2f" : "#5f6874";
}

async function loadConfig() {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("Failed to load config");
  const data = await res.json();
  saveDirInput.value = data.save_dir;
  hotkeyInput.value = data.hotkey;
}

function toLocalTime(iso) {
  const date = new Date(iso);
  return date.toLocaleString();
}

function renderGallery(items) {
  if (!items.length) {
    galleryNode.innerHTML = "<p>No screenshots yet.</p>";
    return;
  }
  galleryNode.innerHTML = items
    .map(
      (item) => `
      <article class="card">
        <a href="${item.url}" target="_blank" rel="noopener noreferrer">
          <img src="${item.url}?t=${Date.now()}" alt="${item.filename}" />
        </a>
        <div class="meta">
          <div>${item.filename}</div>
          <div>${toLocalTime(item.modified)}</div>
          <div>${Math.round(item.size / 1024)} KB</div>
        </div>
      </article>
      `
    )
    .join("");
}

async function refreshGallery() {
  const res = await fetch("/api/screenshots");
  if (!res.ok) throw new Error("Failed to load screenshots");
  const data = await res.json();
  renderGallery(data);
}

document.getElementById("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Saving...");

  const payload = {
    save_dir: saveDirInput.value.trim(),
    hotkey: hotkeyInput.value.trim(),
  };

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to save settings");
    setStatus(`Saved. Current hotkey: ${data.hotkey}`);
    await refreshGallery();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("capture-btn").addEventListener("click", async () => {
  setStatus("Capturing...");
  try {
    const res = await fetch("/api/capture", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Capture failed");
    setStatus(`Saved screenshot: ${data.filename}`);
    await refreshGallery();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("refresh-btn").addEventListener("click", async () => {
  try {
    await refreshGallery();
    setStatus("Gallery refreshed");
  } catch (err) {
    setStatus(err.message, true);
  }
});

(async () => {
  try {
    await loadConfig();
    await refreshGallery();
    setStatus("Ready");
  } catch (err) {
    setStatus(err.message, true);
  }
})();

setInterval(() => {
  refreshGallery().catch(() => {});
}, 5000);
