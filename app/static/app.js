const state = {
  tracks: [],
  playlists: [],
  selectedPlaylistId: null,
};

function el(id) { return document.getElementById(id); }

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function activateView(name) {
  document.querySelectorAll('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
}

function renderStats(stats) {
  let lines = [`Tracks: ${stats.count}`];
  for (const [src, cnt] of Object.entries(stats.by_source || {})) {
    lines.push(`${src}: ${cnt}`);
  }
  lines.push(`Size: ${(stats.size_bytes / (1024*1024)).toFixed(1)} MB`);
  el('stats').innerText = lines.join('\n');
}

function playTrack(track) {
  const audio = el('audio');
  audio.src = `/api/audio/${track.id}`;
  audio.play();
  el('now-playing').innerText = `${track.source.toUpperCase()}  ${track.name}`;
}

function renderTracks() {
  const tbody = el('track-rows');
  tbody.innerHTML = '';
  for (const t of state.tracks) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge ${t.source}">${t.source}</span></td>
      <td>${t.name}</td>
      <td>${t.rel_path}</td>
      <td>
        <button data-play="${t.id}">Play</button>
        <button data-add="${t.id}">Add to Playlist</button>
      </td>`;
    tr.querySelector('[data-play]').onclick = () => playTrack(t);
    tr.querySelector('[data-add]').onclick = async () => {
      if (!state.selectedPlaylistId) return alert('Select a playlist first.');
      await api(`/api/playlists/${state.selectedPlaylistId}/tracks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track_id: t.id }),
      });
      await loadPlaylistDetail();
    };
    tbody.appendChild(tr);
  }
}

async function loadTracks() {
  const q = encodeURIComponent(el('search').value.trim());
  const source = encodeURIComponent(el('source-filter').value);
  const data = await api(`/api/library/tracks?query=${q}&source=${source}`);
  state.tracks = data.tracks;
  renderTracks();
}

function renderPlaylists() {
  const ul = el('playlist-list');
  ul.innerHTML = '';
  for (const p of state.playlists) {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.textContent = p.name;
    b.onclick = async () => {
      state.selectedPlaylistId = p.id;
      await loadPlaylistDetail();
    };
    li.appendChild(b);
    ul.appendChild(li);
  }
}

async function loadPlaylists() {
  const data = await api('/api/playlists');
  state.playlists = data.playlists;
  renderPlaylists();
}

async function loadPlaylistDetail() {
  if (!state.selectedPlaylistId) return;
  const data = await api(`/api/playlists/${state.selectedPlaylistId}`);
  el('playlist-title').innerText = `${data.playlist.name} (${data.tracks.length})`;
  const ul = el('playlist-tracks');
  ul.innerHTML = '';
  for (const t of data.tracks) {
    const li = document.createElement('li');
    li.innerHTML = `<span>${t.name}</span><span><button data-play>Play</button> <button data-remove>Remove</button></span>`;
    li.querySelector('[data-play]').onclick = () => playTrack(t);
    li.querySelector('[data-remove]').onclick = async () => {
      await fetch(`/api/playlists/${state.selectedPlaylistId}/tracks/${t.id}`, { method: 'DELETE' });
      await loadPlaylistDetail();
    };
    ul.appendChild(li);
  }
}

async function createPlaylist() {
  const name = el('new-playlist-name').value.trim();
  if (!name) return;
  await api('/api/playlists', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  el('new-playlist-name').value = '';
  await loadPlaylists();
}

function renderJobs(jobs) {
  const tbody = el('job-rows');
  tbody.innerHTML = '';
  for (const j of jobs) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="status ${j.status}">${j.status}</td>
      <td>${j.provider}</td>
      <td>${j.prompt}</td>
      <td>${j.updated_at}</td>
      <td>${j.detail || ''}</td>`;
    tbody.appendChild(tr);
  }
}

async function loadJobs() {
  const data = await api('/api/jobs');
  renderJobs(data.jobs);
}

async function startGeneration(provider, form) {
  const payload = {
    provider,
    prompt: form.prompt.value,
    max_new_tokens: Number(form.max_new_tokens.value),
    guidance_scale: Number(form.guidance_scale.value),
  };
  await api('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  form.reset();
  alert(`${provider} generation job queued`);
  activateView('jobs');
  await loadJobs();
}

async function bootstrap() {
  document.querySelectorAll('.nav-btn').forEach((b) => b.onclick = () => activateView(b.dataset.view));
  el('refresh-library').onclick = loadTracks;
  el('search').oninput = loadTracks;
  el('source-filter').onchange = loadTracks;
  el('create-playlist').onclick = createPlaylist;
  el('refresh-jobs').onclick = loadJobs;
  el('gen-suno').onsubmit = async (e) => { e.preventDefault(); await startGeneration('suno', e.target); };

  const stats = await api('/api/library/stats');
  renderStats(stats);
  await loadTracks();
  await loadPlaylists();
  await loadJobs();
}

bootstrap().catch((err) => {
  console.error(err);
  alert(`Failed to load app: ${err.message}`);
});
