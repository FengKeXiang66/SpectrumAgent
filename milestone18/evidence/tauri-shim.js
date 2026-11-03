// Browser-only IPC bridge. Production dist and frontend modules stay unchanged.
// All data operations use an isolated real FastAPI app; engine phases and
// TASK18 agent response batches are controlled acceptance fixtures.
(() => {
  const callbacks = new Map();
  let nextCallback = 0;
  window.__TAURI_INTERNALS__ = {
    transformCallback(callback) { const id = ++nextCallback; callbacks.set(id, callback); return id; },
    async invoke(command, args = {}) {
      if (command === 'plugin:event|listen') return args.handler;
      if (command === 'plugin:event|unlisten' || command === 'boot_probe') return null;
      const response = await fetch('/ipc', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, args, phase: new URLSearchParams(location.search).get('phase') ?? 'Ready' }),
      });
      const value = await response.json();
      if (!response.ok) throw value;
      return value;
    },
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener(_event, id) { callbacks.delete(id); } };
  // Dismiss only the existing optional shortcut primer in this test origin.
  localStorage.setItem('spectrum.annotation.shortcuts.seen.v1', 'yes');
})();
