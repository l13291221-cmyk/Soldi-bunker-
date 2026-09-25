// Funzioni condivise: modal PIN admin + toast
function toast(msg) {
  let t = document.querySelector('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), 2400);
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formatMoney(cents, currency = 'eur') {
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: currency.toUpperCase() }).format(cents / 100);
}

(function adminButton() {
  const btn = document.getElementById('adminBtn');
  if (!btn) return;
  const bg = document.createElement('div');
  bg.className = 'modal-bg';
  bg.innerHTML = `
    <form class="modal" autocomplete="off">
      <h3>Area riservata</h3>
      <p class="muted small" style="margin:0">Inserisci il PIN per accedere.</p>
      <input class="pin-input" type="password" inputmode="numeric" maxlength="16" required aria-label="PIN">
      <p class="err"></p>
      <button class="btn btn-gold" style="width:100%" type="submit">Entra</button>
    </form>`;
  document.body.appendChild(bg);
  const form = bg.querySelector('form');
  const input = bg.querySelector('input');
  const err = bg.querySelector('.err');

  btn.addEventListener('click', async () => {
    const me = await fetch('/api/admin/me').then(r => r.json()).catch(() => ({}));
    if (me.admin) { location.href = '/admin'; return; }
    err.textContent = ''; input.value = '';
    bg.classList.add('open');
    setTimeout(() => input.focus(), 50);
  });
  bg.addEventListener('click', e => { if (e.target === bg) bg.classList.remove('open'); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') bg.classList.remove('open'); });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    err.textContent = '';
    const r = await fetch('/api/admin/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: input.value }),
    });
    if (r.ok) { location.href = '/admin'; return; }
    const d = await r.json().catch(() => ({}));
    err.textContent = d.error || 'Errore';
    form.classList.remove('shake'); void form.offsetWidth; form.classList.add('shake');
    input.select();
  });
})();
