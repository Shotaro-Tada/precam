const $ = (sel) => document.querySelector(sel);

async function load() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      { libraries: { "PreCAM-Shotaro": ["General"] } },
      resolve
    );
  });
}

async function save(settings) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(settings, resolve);
  });
}

function flash(text) {
  const el = $("#msg");
  el.textContent = text;
  setTimeout(() => (el.textContent = ""), 2000);
}

async function render() {
  const settings = await load();
  const container = $("#lib-list");
  container.innerHTML = "";

  for (const [libName, folders] of Object.entries(settings.libraries)) {
    const block = document.createElement("div");
    block.className = "lib-block";

    const header = document.createElement("div");
    header.className = "lib-header";
    header.innerHTML = `<span>${libName}</span><button data-lib="${libName}" title="Remove library">&times;</button>`;
    block.appendChild(header);

    for (const folder of folders) {
      const item = document.createElement("div");
      item.className = "list-item";
      item.innerHTML = `<span>${folder}</span><button data-lib="${libName}" data-folder="${folder}" title="Remove folder">&times;</button>`;
      block.appendChild(item);
    }

    const addRow = document.createElement("div");
    addRow.className = "folder-add";
    addRow.innerHTML = `<input type="text" placeholder="New folder..." data-lib="${libName}"><button class="btn-add" data-lib="${libName}">+</button>`;
    block.appendChild(addRow);

    container.appendChild(block);
  }

  container.querySelectorAll(".lib-header button[data-lib]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const settings = await load();
      delete settings.libraries[btn.dataset.lib];
      await save(settings);
      flash("Library removed");
      render();
    });
  });

  container.querySelectorAll(".list-item button[data-folder]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const settings = await load();
      const lib = btn.dataset.lib;
      settings.libraries[lib] = (settings.libraries[lib] || []).filter(
        (f) => f !== btn.dataset.folder
      );
      await save(settings);
      flash("Folder removed");
      render();
    });
  });

  container.querySelectorAll(".folder-add .btn-add").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const lib = btn.dataset.lib;
      const input = btn.parentElement.querySelector("input");
      const folder = input.value.trim();
      if (!folder) return;
      input.value = "";
      const settings = await load();
      if (!settings.libraries[lib]) settings.libraries[lib] = [];
      if (!settings.libraries[lib].includes(folder)) {
        settings.libraries[lib].push(folder);
        await save(settings);
        flash("Folder added");
      }
      render();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  render();

  $("#add-lib").addEventListener("click", async () => {
    const input = $("#new-lib");
    const name = input.value.trim();
    if (!name) return;
    input.value = "";
    const settings = await load();
    if (!settings.libraries[name]) {
      settings.libraries[name] = ["General"];
      await save(settings);
      flash("Library added");
    }
    render();
  });
});
