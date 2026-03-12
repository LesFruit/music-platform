const state = {
  tracks: [],
  recentTracks: [],
  playlists: [],
  selectedPlaylistId: null,
  artists: [],
  albums: [],
  currentTrackId: null,
  viewMode: 'list', // 'grid' or 'list'
  currentMobileTab: 'home', // mobile tab navigation
  // Playback state
  isPlaying: false,
  queue: [],
  queueIndex: -1,
  shuffle: false,
  repeat: 'off', // 'off', 'all', 'one'
  volume: 0.7,
  isMuted: false,
  currentTime: 0,
  duration: 0,
};

function el(id) { return document.getElementById(id); }

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function activateView(name) {
  document.querySelectorAll('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('.mobile-tab').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
  state.currentMobileTab = name;
  // Load data for mobile views
  if (name === 'home') {
    loadHomeRecent();
  }
}

// Load recent tracks for home view
async function loadHomeRecent() {
  const data = await api('/api/library/recent?limit=6');
  renderGridView(data.tracks, 'home-recent-grid');
}

// Mobile search functionality
async function performMobileSearch(query) {
  if (!query.trim()) {
    el('mobile-search-results').innerHTML = '';
    return;
  }
  const data = await api(`/api/library/tracks?query=${encodeURIComponent(query)}&limit=20`);
  renderGridView(data.tracks, 'mobile-search-results');
}

// Initialize swipe gestures
function initSwipeGestures() {
  const main = el('main');
  if (!main) return;

  let touchStartX = 0;
  let touchEndX = 0;
  const minSwipeDistance = 50;

  const mobileTabs = ['home', 'browse', 'search', 'library'];

  main.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
  }, { passive: true });

  main.addEventListener('touchend', (e) => {
    touchEndX = e.changedTouches[0].screenX;
    const swipeDistance = touchEndX - touchStartX;

    if (Math.abs(swipeDistance) > minSwipeDistance) {
      const currentIdx = mobileTabs.indexOf(state.currentMobileTab);

      if (swipeDistance > 0 && currentIdx > 0) {
        // Swipe right - go to previous tab
        activateView(mobileTabs[currentIdx - 1]);
      } else if (swipeDistance < 0 && currentIdx < mobileTabs.length - 1) {
        // Swipe left - go to next tab
        activateView(mobileTabs[currentIdx + 1]);
      }
    }
  }, { passive: true });
}

// Handle mobile source filter clicks
function initMobileSourceFilters() {
  document.querySelectorAll('.source-chip').forEach((chip) => {
    chip.onclick = async () => {
      const source = chip.dataset.source;
      // Set the source filter and navigate to library
      el('source-filter').value = source;
      el('mobile-search').value = '';
      activateView('library');
      await loadTracks();
    };
  });
}

// Initialize mobile quick actions
function initMobileQuickActions() {
  document.querySelectorAll('.quick-action').forEach((btn) => {
    btn.onclick = () => activateView(btn.dataset.view);
  });
  document.querySelectorAll('.view-all').forEach((btn) => {
    btn.onclick = () => activateView(btn.dataset.view);
  });
  document.querySelectorAll('.browse-card').forEach((card) => {
    card.onclick = () => activateView(card.dataset.view);
  });
}

function renderStats(stats) {
  let lines = [`Tracks: ${stats.count}`];
  for (const [src, cnt] of Object.entries(stats.by_source || {})) {
    lines.push(`${src}: ${cnt}`);
  }
  lines.push(`Size: ${(stats.size_bytes / (1024*1024)).toFixed(1)} MB`);
  el('stats').innerText = lines.join('\n');
}

// ==================== PLAYBACK CONTROLS ====================

const audio = el('audio');

function formatTime(seconds) {
  if (isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function updatePlayerUI() {
  // Play/pause icon
  el('icon-play').style.display = state.isPlaying ? 'none' : 'block';
  el('icon-pause').style.display = state.isPlaying ? 'block' : 'none';
  
  // Shuffle button
  el('btn-shuffle').classList.toggle('active', state.shuffle);
  
  // Repeat button
  const repeatBtn = el('btn-repeat');
  const repeatBadge = el('repeat-badge');
  repeatBtn.classList.toggle('active', state.repeat !== 'off');
  if (state.repeat === 'one') {
    repeatBadge.style.display = 'block';
    repeatBadge.textContent = '1';
  } else {
    repeatBadge.style.display = 'none';
  }
  
  // Progress
  const progress = state.duration > 0 ? (state.currentTime / state.duration) * 100 : 0;
  el('progress-fill').style.width = `${progress}%`;
  el('progress-handle').style.left = `${progress}%`;
  el('current-time').textContent = formatTime(state.currentTime);
  el('duration').textContent = formatTime(state.duration);
  
  // Volume
  const volumePercent = state.isMuted ? 0 : state.volume * 100;
  el('volume-fill').style.width = `${volumePercent}%`;
  el('icon-volume').style.display = state.isMuted || state.volume === 0 ? 'none' : 'block';
  el('icon-mute').style.display = state.isMuted || state.volume === 0 ? 'block' : 'none';
  
  // Prev/Next buttons
  el('btn-prev').disabled = state.queue.length === 0;
  el('btn-next').disabled = state.queue.length === 0;
}

function updateNowPlaying(track, metadata) {
  if (!track) {
    el('now-playing-title').textContent = 'Nothing playing';
    el('now-playing-artist').textContent = '-';
    el('player-artwork').innerHTML = '<div class="artwork-placeholder-small">♪</div>';
    return;
  }
  
  el('now-playing-title').textContent = metadata?.title || track.name;
  el('now-playing-artist').textContent = metadata?.artist || track.source;
  
  const artworkEl = el('player-artwork');
  if (metadata?.artwork_url) {
    artworkEl.innerHTML = `<img src="${metadata.artwork_url}" alt="" />`;
  } else {
    artworkEl.innerHTML = '<div class="artwork-placeholder-small">♪</div>';
  }
}

function playTrackFromQueue() {
  if (state.queueIndex < 0 || state.queueIndex >= state.queue.length) {
    state.isPlaying = false;
    updatePlayerUI();
    return;
  }
  
  const item = state.queue[state.queueIndex];
  const track = item.track;
  const metadata = item.metadata || {};
  
  state.currentTrackId = track.id;
  audio.src = `/api/audio/${track.id}`;
  audio.play().then(() => {
    state.isPlaying = true;
    updateNowPlaying(track, metadata);
    updatePlayerUI();
    updateQueueUI();
  }).catch(err => {
    console.error('Playback error:', err);
    state.isPlaying = false;
    updatePlayerUI();
  });
}

function playTrack(track, metadata = null) {
  // If metadata not provided, find it from current tracks
  if (!metadata) {
    const item = state.tracks.find(t => t.track.id === track.id);
    metadata = item?.metadata || {};
  }
  
  // Add to queue if not already playing from queue
  if (state.queue.length === 0 || state.queue[state.queueIndex]?.track.id !== track.id) {
    state.queue = [{ track, metadata }];
    state.queueIndex = 0;
  }
  
  playTrackFromQueue();
}

function playTrackWithContext(track, allTracks, startIndex) {
  // Build queue from all tracks starting at startIndex
  state.queue = allTracks.slice(startIndex).map(item => ({
    track: item.track,
    metadata: item.metadata || {}
  }));
  state.queueIndex = 0;
  
  // Add remaining tracks before startIndex for continuous playback
  const beforeTracks = allTracks.slice(0, startIndex).map(item => ({
    track: item.track,
    metadata: item.metadata || {}
  }));
  state.queue = state.queue.concat(beforeTracks);
  
  playTrackFromQueue();
}

function togglePlay() {
  if (!audio.src) return;
  
  if (state.isPlaying) {
    audio.pause();
    state.isPlaying = false;
  } else {
    audio.play().then(() => {
      state.isPlaying = true;
    }).catch(console.error);
  }
  updatePlayerUI();
}

function playNext() {
  if (state.queue.length === 0) return;
  
  if (state.shuffle) {
    // Pick random index different from current
    let newIndex;
    do {
      newIndex = Math.floor(Math.random() * state.queue.length);
    } while (newIndex === state.queueIndex && state.queue.length > 1);
    state.queueIndex = newIndex;
  } else {
    state.queueIndex++;
    if (state.queueIndex >= state.queue.length) {
      if (state.repeat === 'all') {
        state.queueIndex = 0;
      } else {
        state.queueIndex = state.queue.length - 1;
        state.isPlaying = false;
        audio.pause();
        updatePlayerUI();
        return;
      }
    }
  }
  
  playTrackFromQueue();
}

function playPrevious() {
  if (state.queue.length === 0) return;
  
  // If more than 3 seconds into track, restart it
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  
  if (state.shuffle) {
    let newIndex;
    do {
      newIndex = Math.floor(Math.random() * state.queue.length);
    } while (newIndex === state.queueIndex && state.queue.length > 1);
    state.queueIndex = newIndex;
  } else {
    state.queueIndex--;
    if (state.queueIndex < 0) {
      if (state.repeat === 'all') {
        state.queueIndex = state.queue.length - 1;
      } else {
        state.queueIndex = 0;
        return;
      }
    }
  }
  
  playTrackFromQueue();
}

function toggleShuffle() {
  state.shuffle = !state.shuffle;
  updatePlayerUI();
}

function toggleRepeat() {
  const modes = ['off', 'all', 'one'];
  const currentIndex = modes.indexOf(state.repeat);
  state.repeat = modes[(currentIndex + 1) % modes.length];
  updatePlayerUI();
}

function seek(percent) {
  if (state.duration > 0) {
    audio.currentTime = (percent / 100) * state.duration;
  }
}

function setVolume(percent) {
  state.volume = Math.max(0, Math.min(1, percent / 100));
  audio.volume = state.volume;
  if (state.volume > 0 && state.isMuted) {
    state.isMuted = false;
  }
  updatePlayerUI();
}

function toggleMute() {
  state.isMuted = !state.isMuted;
  audio.muted = state.isMuted;
  updatePlayerUI();
}

// ==================== QUEUE UI ====================

function updateQueueUI() {
  const list = el('queue-list');
  if (!list) return;
  
  if (state.queue.length === 0) {
    list.innerHTML = '<li class="queue-empty">Queue is empty</li>';
    return;
  }
  
  list.innerHTML = '';
  state.queue.forEach((item, index) => {
    const track = item.track;
    const metadata = item.metadata || {};
    const li = document.createElement('li');
    li.className = index === state.queueIndex ? 'current' : '';
    li.innerHTML = `
      <span class="queue-number">${index === state.queueIndex ? '▶' : index + 1}</span>
      <div class="queue-info">
        <div class="queue-title">${metadata.title || track.name}</div>
        <div class="queue-artist">${metadata.artist || track.source}</div>
      </div>
      <button class="queue-remove" data-index="${index}">&times;</button>
    `;
    li.onclick = (e) => {
      if (e.target.classList.contains('queue-remove')) {
        e.stopPropagation();
        removeFromQueue(index);
      } else {
        state.queueIndex = index;
        playTrackFromQueue();
      }
    };
    list.appendChild(li);
  });
}

function showQueueModal() {
  el('queue-modal').style.display = 'flex';
  updateQueueUI();
}

function hideQueueModal() {
  el('queue-modal').style.display = 'none';
}

function removeFromQueue(index) {
  state.queue.splice(index, 1);
  if (index < state.queueIndex) {
    state.queueIndex--;
  } else if (index === state.queueIndex) {
    // Removed current track, play next
    if (state.queueIndex >= state.queue.length) {
      state.queueIndex = 0;
    }
    if (state.queue.length > 0) {
      playTrackFromQueue();
    } else {
      audio.pause();
      audio.src = '';
      state.isPlaying = false;
      state.currentTrackId = null;
      updateNowPlaying(null, null);
    }
  }
  updateQueueUI();
}

function clearQueue() {
  state.queue = [];
  state.queueIndex = -1;
  audio.pause();
  audio.src = '';
  state.isPlaying = false;
  state.currentTrackId = null;
  updateNowPlaying(null, null);
  updateQueueUI();
}

function shuffleQueue() {
  if (state.queue.length < 2) return;
  
  // Keep current track at current position, shuffle the rest
  const current = state.queue[state.queueIndex];
  const rest = state.queue.filter((_, i) => i !== state.queueIndex);
  
  // Fisher-Yates shuffle
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  
  state.queue = [current, ...rest];
  state.queueIndex = 0;
  updateQueueUI();
}

// ==================== PROGRESS BAR DRAGGING ====================

let isDraggingProgress = false;

function initProgressBar() {
  const container = el('progress-container');
  const handle = el('progress-handle');
  
  function getPercentFromEvent(e) {
    const rect = container.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    return (x / rect.width) * 100;
  }
  
  function updateProgress(percent) {
    el('progress-fill').style.width = `${percent}%`;
    el('progress-handle').style.left = `${percent}%`;
  }
  
  container.addEventListener('mousedown', (e) => {
    isDraggingProgress = true;
    container.classList.add('dragging');
    const percent = getPercentFromEvent(e);
    updateProgress(percent);
  });
  
  container.addEventListener('touchstart', (e) => {
    isDraggingProgress = true;
    container.classList.add('dragging');
    const percent = getPercentFromEvent(e);
    updateProgress(percent);
  }, { passive: true });
  
  document.addEventListener('mousemove', (e) => {
    if (!isDraggingProgress) return;
    const percent = getPercentFromEvent(e);
    updateProgress(percent);
  });
  
  document.addEventListener('touchmove', (e) => {
    if (!isDraggingProgress) return;
    const percent = getPercentFromEvent(e);
    updateProgress(percent);
  }, { passive: true });
  
  document.addEventListener('mouseup', (e) => {
    if (!isDraggingProgress) return;
    isDraggingProgress = false;
    container.classList.remove('dragging');
    const percent = getPercentFromEvent(e);
    seek(percent);
  });
  
  document.addEventListener('touchend', (e) => {
    if (!isDraggingProgress) return;
    isDraggingProgress = false;
    container.classList.remove('dragging');
    // Use changedTouches for touchend
    const rect = container.getBoundingClientRect();
    const clientX = e.changedTouches[0].clientX;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    const percent = (x / rect.width) * 100;
    seek(percent);
  });
}

function initVolumeSlider() {
  const container = el('volume-container');
  
  function getPercentFromEvent(e) {
    const rect = container.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    return (x / rect.width) * 100;
  }
  
  container.addEventListener('click', (e) => {
    const percent = getPercentFromEvent(e);
    setVolume(percent);
  });
  
  container.addEventListener('mousedown', (e) => {
    const percent = getPercentFromEvent(e);
    setVolume(percent);
    
    function onMouseMove(ev) {
      setVolume(getPercentFromEvent(ev));
    }
    
    function onMouseUp() {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    }
    
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

// ==================== AUDIO EVENTS ====================

function initAudioEvents() {
  audio.addEventListener('timeupdate', () => {
    if (!isDraggingProgress) {
      state.currentTime = audio.currentTime;
      state.duration = audio.duration || 0;
      updatePlayerUI();
    }
  });
  
  audio.addEventListener('loadedmetadata', () => {
    state.duration = audio.duration || 0;
    updatePlayerUI();
  });
  
  audio.addEventListener('ended', () => {
    if (state.repeat === 'one') {
      audio.currentTime = 0;
      audio.play().catch(console.error);
    } else {
      playNext();
    }
  });
  
  audio.addEventListener('play', () => {
    state.isPlaying = true;
    updatePlayerUI();
  });
  
  audio.addEventListener('pause', () => {
    state.isPlaying = false;
    updatePlayerUI();
  });
  
  // Set initial volume
  audio.volume = state.volume;
}

// ==================== PLAYER CONTROLS INIT ====================

function initPlayerControls() {
  el('btn-play').onclick = togglePlay;
  el('btn-prev').onclick = playPrevious;
  el('btn-next').onclick = playNext;
  el('btn-shuffle').onclick = toggleShuffle;
  el('btn-repeat').onclick = toggleRepeat;
  el('btn-mute').onclick = toggleMute;
  el('btn-queue').onclick = showQueueModal;
  el('close-queue').onclick = hideQueueModal;
  el('clear-queue').onclick = clearQueue;
  el('shuffle-queue').onclick = shuffleQueue;
  
  // Close modal on backdrop click
  el('queue-modal').onclick = (e) => {
    if (e.target === el('queue-modal')) {
      hideQueueModal();
    }
  };
  
  initProgressBar();
  initVolumeSlider();
  initAudioEvents();
  updatePlayerUI();
}

// ==================== RENDER FUNCTIONS ====================

function renderTracks() {
  const tbody = el('track-rows');
  tbody.innerHTML = '';
  for (const item of state.tracks) {
    const t = item.track;
    const m = item.metadata || {};
    const tr = document.createElement('tr');
    // Artwork thumbnail
    const artworkHtml = m.artwork_url
      ? `<img src="${m.artwork_url}" class="track-thumb" />`
      : '<div class="track-thumb-placeholder">♪</div>';
    const publishBtn = m.publish_state === 1
      ? '<button class="publish-btn published" data-publish="0">Published</button>'
      : '<button class="publish-btn" data-publish="1">Publish</button>';
    tr.innerHTML = `
      <td>${artworkHtml}</td>
      <td><span class="badge ${t.source}">${t.source}</span></td>
      <td>${m.title || t.name}</td>
      <td>${m.artist || '-'}</td>
      <td>${m.album || '-'}</td>
      <td>${m.genre || '-'}</td>
      <td>
        <button data-play="${t.id}">Play</button>
        <button data-add="${t.id}">Add to Playlist</button>
        ${publishBtn}
      </td>`;
    tr.querySelector('[data-play]').onclick = () => {
      const index = state.tracks.findIndex(trackItem => trackItem.track.id === t.id);
      playTrackWithContext(t, state.tracks, index);
    };
    tr.querySelector('[data-add]').onclick = async () => {
      if (!state.selectedPlaylistId) return alert('Select a playlist first.');
      await api(`/api/playlists/${state.selectedPlaylistId}/tracks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track_id: t.id }),
      });
      await loadPlaylistDetail();
    };
    tr.querySelector('[data-publish]').onclick = async (e) => {
      const newState = parseInt(e.target.dataset.publish);
      await api(`/api/tracks/${t.id}/metadata`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ publish_state: newState }),
      });
      await loadTracks();
    };
    tbody.appendChild(tr);
  }
}

function renderGridView(tracks, containerId) {
  const container = el(containerId);
  container.innerHTML = '';
  for (const item of tracks) {
    const t = item.track;
    const m = item.metadata || {};
    const card = document.createElement('div');
    card.className = 'track-card';
    const artworkHtml = m.artwork_url
      ? `<img src="${m.artwork_url}" class="card-artwork" />`
      : '<div class="card-artwork-placeholder">♪</div>';
    card.innerHTML = `
      ${artworkHtml}
      <div class="card-info">
        <div class="card-title">${m.title || t.name}</div>
        <div class="card-artist">${m.artist || 'Unknown Artist'}</div>
        <div class="card-meta">
          <span class="badge ${t.source}">${t.source}</span>
        </div>
      </div>
      <div class="card-actions">
        <button data-play="${t.id}">Play</button>
      </div>
    `;
    card.querySelector('[data-play]').onclick = () => {
      // Find index in tracks array for context
      const allItems = containerId === 'track-grid' ? state.tracks : 
                       containerId === 'recent-grid' ? state.recentTracks : tracks;
      const index = allItems.findIndex(trackItem => trackItem.track.id === t.id);
      playTrackWithContext(t, allItems, index);
    };
    container.appendChild(card);
  }
}

function updateViewMode() {
  const grid = el('track-grid');
  const table = el('track-table');
  const toggleBtn = el('view-toggle');

  if (state.viewMode === 'grid') {
    grid.style.display = 'grid';
    table.style.display = 'none';
    toggleBtn.classList.add('grid-active');
    renderGridView(state.tracks, 'track-grid');
  } else {
    grid.style.display = 'none';
    table.style.display = 'table';
    toggleBtn.classList.remove('grid-active');
  }
}

function toggleViewMode() {
  state.viewMode = state.viewMode === 'list' ? 'grid' : 'list';
  localStorage.setItem('music-platform-view-mode', state.viewMode);
  updateViewMode();
}

async function loadTracks() {
  const q = encodeURIComponent(el('search').value.trim());
  const source = encodeURIComponent(el('source-filter').value);
  const publishState = encodeURIComponent(el('publish-filter').value);
  const artist = encodeURIComponent(el('artist-filter').value.trim());
  const album = encodeURIComponent(el('album-filter').value.trim());
  const genre = encodeURIComponent(el('genre-filter').value.trim());
  const sortBy = encodeURIComponent(el('sort-by').value);
  const sortOrder = encodeURIComponent(el('sort-order').value);
  const data = await api(`/api/library/tracks?query=${q}&source=${source}&publish_state=${publishState}&artist=${artist}&album=${album}&genre=${genre}&sort_by=${sortBy}&sort_order=${sortOrder}`);
  state.tracks = data.tracks;
  renderTracks();
  if (state.viewMode === 'grid') {
    renderGridView(state.tracks, 'track-grid');
  }
}

async function loadRecentlyAdded() {
  const data = await api('/api/library/recent');
  state.recentTracks = data.tracks;
  renderRecentlyAdded();
}

function renderRecentlyAdded() {
  const tbody = el('recent-rows');
  tbody.innerHTML = '';
  for (const item of state.recentTracks) {
    const t = item.track;
    const m = item.metadata || {};
    const tr = document.createElement('tr');
    const artworkHtml = m.artwork_url
      ? `<img src="${m.artwork_url}" class="track-thumb" />`
      : '<div class="track-thumb-placeholder">♪</div>';
    const indexedDate = t.indexed_at ? new Date(t.indexed_at).toLocaleDateString() : '-';
    tr.innerHTML = `
      <td>${artworkHtml}</td>
      <td><span class="badge ${t.source}">${t.source}</span></td>
      <td>${m.title || t.name}</td>
      <td>${m.artist || '-'}</td>
      <td>${m.album || '-'}</td>
      <td>${indexedDate}</td>
      <td>
        <button data-play="${t.id}">Play</button>
      </td>`;
    tr.querySelector('[data-play]').onclick = () => {
      const index = state.recentTracks.findIndex(trackItem => trackItem.track.id === t.id);
      playTrackWithContext(t, state.recentTracks, index);
    };
    tbody.appendChild(tr);
  }
  // Also render grid view
  renderGridView(state.recentTracks, 'recent-grid');
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
  // Show delete button when a playlist is selected
  const deleteBtn = el('delete-playlist');
  if (deleteBtn) deleteBtn.style.display = 'inline-block';
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
  
  // Add play all button functionality
  if (data.tracks.length > 0) {
    const playAllBtn = document.createElement('button');
    playAllBtn.textContent = 'Play All';
    playAllBtn.style.marginBottom = '10px';
    playAllBtn.onclick = () => {
      const queueItems = data.tracks.map(t => ({ track: t, metadata: {} }));
      state.queue = queueItems;
      state.queueIndex = 0;
      playTrackFromQueue();
    };
    ul.insertBefore(playAllBtn, ul.firstChild);
  }
}

async function deletePlaylist() {
  if (!state.selectedPlaylistId) return;
  if (!confirm('Delete this playlist?')) return;
  await api(`/api/playlists/${state.selectedPlaylistId}`, { method: 'DELETE' });
  state.selectedPlaylistId = null;
  el('playlist-title').innerText = 'Playlist Tracks';
  const deleteBtn = el('delete-playlist');
  if (deleteBtn) deleteBtn.style.display = 'none';
  await loadPlaylists();
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

// Artists view
async function loadArtists() {
  const q = encodeURIComponent(el('artist-search')?.value?.trim() || '');
  const data = await api(`/api/artists?q=${q}`);
  state.artists = data.artists;
  renderArtists();
}

function renderArtists() {
  const container = el('artist-list');
  container.innerHTML = '';
  for (const artist of state.artists) {
    const card = document.createElement('div');
    card.className = 'card artist-card';
    card.innerHTML = `
      <h3>${artist.name}</h3>
      <p>${artist.track_count} tracks</p>
    `;
    card.onclick = () => loadArtistDetail(artist.name);
    container.appendChild(card);
  }
}

async function loadArtistDetail(artist) {
  const data = await api(`/api/artists/${encodeURIComponent(artist)}`);
  el('artist-name').innerText = data.artist;
  el('artist-track-count').innerText = `${data.track_count} tracks`;
  const tbody = el('artist-track-rows');
  tbody.innerHTML = '';
  for (const t of data.tracks) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button class="link-btn" data-track="${t.id}">${t.title || t.name}</button></td>
      <td>${t.album || '-'}</td>
      <td>${t.genre || '-'}</td>
      <td>
        <button data-play="${t.id}">Play</button>
      </td>`;
    tr.querySelector('[data-play]').onclick = () => {
      const index = data.tracks.findIndex(track => track.id === t.id);
      const queueItems = data.tracks.map(track => ({ track: { ...track, source: track.source || 'unknown' }, metadata: track }));
      state.queue = queueItems;
      state.queueIndex = index;
      playTrackFromQueue();
    };
    tr.querySelector('[data-track]').onclick = () => showTrackDetail(t.id);
    tbody.appendChild(tr);
  }
  activateView('artist-detail');
}

// Albums view
async function loadAlbums() {
  const q = encodeURIComponent(el('album-search')?.value?.trim() || '');
  const data = await api(`/api/albums?q=${q}`);
  state.albums = data.albums;
  renderAlbums();
}

function renderAlbums() {
  const container = el('album-list');
  container.innerHTML = '';
  for (const album of state.albums) {
    const card = document.createElement('div');
    card.className = 'card album-card';
    card.innerHTML = `
      <h3>${album.name}</h3>
      <p>${album.artist || 'Unknown Artist'}</p>
      <p>${album.track_count} tracks</p>
    `;
    card.onclick = () => loadAlbumDetail(album.name);
    container.appendChild(card);
  }
}

async function loadAlbumDetail(album) {
  const data = await api(`/api/albums/${encodeURIComponent(album)}`);
  el('album-name').innerText = data.album;
  el('album-track-count').innerText = `${data.track_count} tracks`;
  const tbody = el('album-track-rows');
  tbody.innerHTML = '';
  for (const t of data.tracks) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button class="link-btn" data-track="${t.id}">${t.title || t.name}</button></td>
      <td>${t.artist || '-'}</td>
      <td>${t.genre || '-'}</td>
      <td>
        <button data-play="${t.id}">Play</button>
      </td>`;
    tr.querySelector('[data-play]').onclick = () => {
      const index = data.tracks.findIndex(track => track.id === t.id);
      const queueItems = data.tracks.map(track => ({ track: { ...track, source: track.source || 'unknown' }, metadata: track }));
      state.queue = queueItems;
      state.queueIndex = index;
      playTrackFromQueue();
    };
    tr.querySelector('[data-track]').onclick = () => showTrackDetail(t.id);
    tbody.appendChild(tr);
  }
  activateView('album-detail');
}

// Track detail view
async function showTrackDetail(trackId) {
  state.currentTrackId = trackId;
  const data = await api(`/api/tracks/${trackId}`);
  const track = data.track;
  const meta = data.metadata;

  // Display artwork
  const artworkEl = el('track-artwork');
  if (meta.artwork_url) {
    artworkEl.innerHTML = `<img src="${meta.artwork_url}" class="track-artwork-img" />`;
  } else {
    artworkEl.innerHTML = '<div class="artwork-placeholder">♪</div>';
  }

  el('track-title').innerText = meta.title || track.name;
  el('track-artist').innerText = meta.artist || 'Unknown Artist';
  el('track-album').innerText = meta.album || 'Unknown Album';

  // Build metadata display
  const metaHtml = [];
  if (meta.publish_state === 1) {
    metaHtml.push('<span class="badge published-badge">Published</span>');
  } else {
    metaHtml.push('<span class="badge hidden-badge">Hidden</span>');
  }
  if (meta.genre) metaHtml.push(`<span class="badge">${meta.genre}</span>`);
  if (meta.bpm) metaHtml.push(`<span>BPM: ${meta.bpm}</span>`);
  if (meta.key) metaHtml.push(`<span>Key: ${meta.key}</span>`);
  if (meta.mood) metaHtml.push(`<span>Mood: ${meta.mood}</span>`);
  if (meta.energy !== null) metaHtml.push(`<span>Energy: ${Math.round(meta.energy * 100)}%</span>`);
  if (meta.tags) metaHtml.push(`<span class="badge">${meta.tags}</span>`);
  el('track-meta').innerHTML = metaHtml.join(' | ');

  // Populate form
  const form = el('metadata-form');
  form.title.value = meta.title || '';
  form.artist.value = meta.artist || '';
  form.album.value = meta.album || '';
  form.genre.value = meta.genre || '';
  form.bpm.value = meta.bpm || '';
  form.key.value = meta.key || '';
  form.mood.value = meta.mood || '';
  form.energy.value = meta.energy ?? '';
  form.tags.value = meta.tags || '';
  form.artwork_url.value = meta.artwork_url || '';
  form.publish_state.value = meta.publish_state ?? 0;
  form.description.value = meta.description || '';

  // Set up play button
  el('play-track').onclick = () => playTrack(track, meta);

  // Set up add to playlist
  el('add-to-playlist').onclick = async () => {
    if (!state.selectedPlaylistId) {
      alert('Select a playlist first in the Playlists view');
      return;
    }
    await api(`/api/playlists/${state.selectedPlaylistId}/tracks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: trackId }),
    });
    alert('Track added to playlist');
  };

  activateView('track-detail');
}

async function bootstrap() {
  // Load saved view mode
  const savedViewMode = localStorage.getItem('music-platform-view-mode');
  if (savedViewMode) {
    state.viewMode = savedViewMode;
  }
  
  // Load saved volume
  const savedVolume = localStorage.getItem('music-platform-volume');
  if (savedVolume !== null) {
    state.volume = parseFloat(savedVolume);
  }

  document.querySelectorAll('.nav-btn').forEach((b) => b.onclick = () => activateView(b.dataset.view));

  // Back button handlers
  document.querySelectorAll('.back-btn').forEach((b) => {
    b.onclick = () => activateView(b.dataset.view);
  });

  el('refresh-library').onclick = loadTracks;
  el('search').oninput = loadTracks;
  el('source-filter').onchange = loadTracks;
  el('publish-filter').onchange = loadTracks;
  el('artist-filter').oninput = loadTracks;
  el('album-filter').oninput = loadTracks;
  el('genre-filter').oninput = loadTracks;
  el('sort-by').onchange = loadTracks;
  el('sort-order').onchange = loadTracks;
  el('view-toggle').onclick = toggleViewMode;
  el('refresh-recent').onclick = loadRecentlyAdded;
  el('create-playlist').onclick = createPlaylist;
  const deletePlaylistBtn = el('delete-playlist');
  if (deletePlaylistBtn) deletePlaylistBtn.onclick = deletePlaylist;
  el('refresh-jobs').onclick = loadJobs;
  el('gen-suno').onsubmit = async (e) => { e.preventDefault(); await startGeneration('suno', e.target); };
  el('gen-musicgen').onsubmit = async (e) => { e.preventDefault(); await startGeneration('musicgen', e.target); };

  // Artists view handlers
  el('artist-search').oninput = loadArtists;

  // Albums view handlers
  el('album-search').oninput = loadAlbums;

  // Track metadata form
  el('metadata-form').onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const payload = {
      title: form.title.value || null,
      artist: form.artist.value || null,
      album: form.album.value || null,
      genre: form.genre.value || null,
      bpm: form.bpm.value ? parseFloat(form.bpm.value) : null,
      key: form.key.value || null,
      mood: form.mood.value || null,
      energy: form.energy.value ? parseFloat(form.energy.value) : null,
      tags: form.tags.value || null,
      artwork_url: form.artwork_url.value || null,
      publish_state: parseInt(form.publish_state.value),
      description: form.description.value || null,
    };
    await api(`/api/tracks/${state.currentTrackId}/metadata`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    alert('Metadata saved');
    await showTrackDetail(state.currentTrackId);
  };

  const stats = await api('/api/library/stats');
  renderStats(stats);
  await loadTracks();
  await loadPlaylists();
  await loadJobs();
  await loadArtists();
  await loadAlbums();
  await loadRecentlyAdded();

  // Apply initial view mode
  updateViewMode();

  // Initialize mobile features
  initSwipeGestures();
  initMobileSourceFilters();
  initMobileQuickActions();

  // Initialize player controls
  initPlayerControls();

  // Mobile search input handler
  const mobileSearch = el('mobile-search');
  if (mobileSearch) {
    let searchTimeout;
    mobileSearch.oninput = () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        performMobileSearch(mobileSearch.value);
      }, 300);
    };
  }

  // Check if mobile and set initial view
  if (window.innerWidth <= 768) {
    activateView('home');
  }
}

bootstrap().catch((err) => {
  console.error(err);
  alert(`Failed to load app: ${err.message}`);
});
