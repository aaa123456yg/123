// 上傳音樂
async function uploadMusic() {
  const files = document.getElementById("musicFiles").files;
  if (!files.length) return;

  const formData = new FormData();
  for (let f of files) formData.append("files", f);

  const res = await fetch("/upload", { method: "POST", body: formData });
  const data = await res.json();

  const list = document.getElementById("uploadedList");
  const existing = new Set([...list.querySelectorAll("li")].map(li => li.textContent.split(" ")[0]));
  data.uploaded.forEach(f => {
    if (existing.has(f)) return; // 🔒 避免重覆顯示
    const li = document.createElement("li");
    li.textContent = f;

    const delBtn = document.createElement("button");
    delBtn.textContent = "刪除";
    delBtn.style.marginLeft = "10px";
    delBtn.onclick = () => li.remove();

    li.appendChild(delBtn);
    list.appendChild(li);
  });
}

// 載入動作
async function loadActions(level) {
  const sections = ["warmup", "core", "cooldown"];
  const list = document.getElementById("actionList");
  list.innerHTML = "";

  for (let section of sections) {
    const res = await fetch(`/get_actions?section=${section}&level=${level}`);
    const actions = await res.json();

    const sectionDiv = document.createElement("div");
    sectionDiv.innerHTML = `<h3>${section.toUpperCase()}</h3>`;
    list.appendChild(sectionDiv);

    actions.forEach(a => {
      const div = document.createElement("div");
      div.className = "action-card";
      div.innerHTML = `
        <input type="checkbox" name="actions" value="${section}|${a.name}">
        <strong>${a.name}</strong><br>
        <img src="${a.gif_url}" width="150"><br>
        <small>${a.audio_text}</small>
      `;
      sectionDiv.appendChild(div);
    });
  }
}
