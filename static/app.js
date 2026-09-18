const $ = (id) => document.getElementById(id);
const dropEl   = $("drop");
const fileEl   = $("file");
const pickEl   = $("pick");
const pickedEl = $("picked");
const uploadEl = $("upload");
const statusEl = $("status");
const listEl   = $("list");
const keyEl    = $("key");

let selected = null;

function setSelected(file) {
  selected = file || null;
  pickedEl.textContent = file ? `${file.name}  (${(file.size/1024).toFixed(1)} KB)` : "";
  uploadEl.disabled = !file;
}

pickEl.addEventListener("click", () => fileEl.click());
fileEl.addEventListener("change", () => setSelected(fileEl.files[0] || null));

["dragenter","dragover"].forEach(ev =>
  dropEl.addEventListener(ev, e => { e.preventDefault(); dropEl.classList.add("drag"); }));
["dragleave","drop"].forEach(ev =>
  dropEl.addEventListener(ev, e => { e.preventDefault(); dropEl.classList.remove("drag"); }));
dropEl.addEventListener("drop", e => {
  const f = e.dataTransfer.files?.[0];
  if (f) setSelected(f);
});

function setStatus(msg, kind) {
  statusEl.hidden = false;
  statusEl.className = "status " + (kind || "");
  statusEl.textContent = msg;
}

uploadEl.addEventListener("click", async () => {
  if (!selected) return;
  uploadEl.disabled = true;
  setStatus("Uploading and extracting…");
  const fd = new FormData();
  fd.append("file", selected);
  try {
    const res = await fetch("/upload", {
      method: "POST",
      headers: keyEl.value ? { "X-API-Key": keyEl.value } : {},
      body: fd,
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || res.statusText);
    setStatus(
      `Uploaded ✓  ${body.chars_extracted} chars extracted\n` +
      `LLM text URL: ${location.origin}${body.text_url}` +
      (body.extract_error ? `\n⚠ extract_error: ${body.extract_error}` : ""),
      "ok"
    );
    setSelected(null);
    fileEl.value = "";
    loadList();
  } catch (err) {
    setStatus("Upload failed: " + err.message, "err");
  } finally {
    uploadEl.disabled = !selected;
  }
});

function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024*1024) return (n/1024).toFixed(1) + " KB";
  return (n/1024/1024).toFixed(2) + " MB";
}

function copy(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const old = btn.textContent;
    btn.textContent = "copied ✓";
    setTimeout(() => (btn.textContent = old), 1200);
  });
}

async function loadList() {
  listEl.innerHTML = "<li class='meta'>Loading…</li>";
  try {
    const res = await fetch("/docs");
    const items = await res.json();
    if (!items.length) {
      listEl.innerHTML = "<li class='meta'>No documents yet.</li>";
      return;
    }
    listEl.innerHTML = "";
    for (const d of items) {
      const li = document.createElement("li");
      const textUrl = location.origin + d.text_url;
      li.innerHTML = `
        <div class="name">${d.filename ?? "(unnamed)"}</div>
        <div class="meta">
          ${fmtBytes(d.size_bytes)} · ${d.chars_extracted} chars ·
          ${new Date(d.uploaded_at).toLocaleString()}
        </div>
        ${d.extract_error ? `<div class="warn">⚠ ${d.extract_error}</div>` : ""}
        <div class="links">
          <a href="${d.text_url}" target="_blank">text</a>
          <a href="${d.raw_url}"  target="_blank">raw</a>
          <a href="${d.meta_url}" target="_blank">meta</a>
          <button class="copy" data-url="${textUrl}">copy LLM URL</button>
        </div>`;
      li.querySelector(".copy").addEventListener("click", (e) =>
        copy(e.target.dataset.url, e.target));
      listEl.appendChild(li);
    }
  } catch (err) {
    listEl.innerHTML = `<li class="warn">Failed to load: ${err.message}</li>`;
  }
}

$("refresh").addEventListener("click", loadList);
loadList();