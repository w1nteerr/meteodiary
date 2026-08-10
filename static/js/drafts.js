/* Офлайн-черновики наблюдений (ТЗ FR-005, п. 4.7.3):
   IndexedDB (не localStorage — фото и лимиты), лимит 10 черновиков,
   идемпотентная отправка по client_uuid, кнопка «Отправить, когда появится сеть». */
(function () {
  const DB = "sinoptik", STORE = "drafts", MAX = 10;

  function openDb() {
    return new Promise((res, rej) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE, { keyPath: "uuid" });
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  }
  const tx = (db, mode) => db.transaction(STORE, mode).objectStore(STORE);
  const all = db => new Promise(r => { const q = tx(db, "readonly").getAll(); q.onsuccess = () => r(q.result); });

  const form = document.getElementById("obs-form");
  const listEl = document.getElementById("drafts-list");
  const card = document.getElementById("drafts-card");
  if (!form) return;

  async function refresh() {
    const db = await openDb();
    const drafts = await all(db);
    card.style.display = drafts.length ? "block" : "none";
    listEl.innerHTML = "";
    for (const d of drafts) {
      const row = document.createElement("p");
      row.innerHTML = `Черновик от ${new Date(d.saved_at).toLocaleString("ru")} ` +
        `(${d.data.observed_at || "без даты"}) `;
      const send = document.createElement("button");
      send.textContent = navigator.onLine ? "Отправить" : "Отправить, когда появится сеть";
      send.disabled = !navigator.onLine;
      send.onclick = () => sendDraft(d);
      const del = document.createElement("button");
      del.textContent = "Удалить"; del.className = "sec"; del.style.marginLeft = "6px";
      del.onclick = async () => { tx(await openDb(), "readwrite").delete(d.uuid); setTimeout(refresh, 100); };
      row.append(send, del);
      listEl.append(row);
    }
  }

  document.getElementById("save-draft")?.addEventListener("click", async () => {
    const db = await openDb();
    const drafts = await all(db);
    if (drafts.length >= MAX) {
      alert("Лимит черновиков (10) исчерпан — отправьте или удалите существующие.");
      return;
    }
    const data = {};
    new FormData(form).forEach((v, k) => {
      if (k === "csrfmiddlewaretoken" || k === "photos") return;
      if (data[k] !== undefined) { data[k] = [].concat(data[k], v); } else { data[k] = v; }
    });
    tx(db, "readwrite").put({ uuid: crypto.randomUUID(), saved_at: Date.now(), data });
    setTimeout(refresh, 100);
    alert("Черновик сохранён на устройстве.");
  });

  async function sendDraft(d) {
    const fd = new FormData();
    Object.entries(d.data).forEach(([k, v]) =>
      [].concat(v).forEach(x => fd.append(k, x)));
    fd.set("client_uuid", d.uuid);
    fd.set("csrfmiddlewaretoken",
      document.querySelector("[name=csrfmiddlewaretoken]").value);
    try {
      const r = await fetch(form.action || location.pathname, {
        method: "POST", body: fd, headers: { "X-Requested-With": "fetch" }});
      if (r.ok || r.status === 400) {
        // 400 с ошибками валидации оставляем черновик; успех/дубликат — удаляем
        const j = await r.json().catch(() => ({}));
        if (j.ok) { tx(await openDb(), "readwrite").delete(d.uuid); setTimeout(refresh, 100);
          alert("Черновик отправлен на модерацию."); }
        else if (j.errors) alert("Ошибки в черновике: " + JSON.stringify(j.errors));
      }
    } catch (e) { alert("Сеть недоступна — черновик сохранён, попробуйте позже."); }
  }

  window.addEventListener("online", refresh);
  window.addEventListener("offline", refresh);
  refresh();
})();
