'use strict';

let activeES = null;

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadSamples('invoice');
  loadSamples('lead');
  loadSamples('ticket');
});

async function loadSamples(agent) {
  try {
    const res = await fetch(`/api/samples/${agent}`);
    const items = await res.json();
    const sel = document.getElementById(`samples-${agent}`);
    sel.innerHTML = '';
    items.forEach((item, i) => {
      const opt = document.createElement('option');
      if (agent === 'invoice') {
        opt.value = item.id;
        opt.textContent = item.name;
      } else if (agent === 'lead') {
        opt.value = item.index;
        opt.textContent = `${item.name} — ${item.role}, ${item.company}`;
      } else {
        opt.value = item.index;
        opt.textContent = `${item.ticket_id}: ${item.subject} [${item.tier}]`;
      }
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error(`Failed to load ${agent} samples:`, e);
  }
}

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(agent) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.tab-btn[data-agent="${agent}"]`).classList.add('active');
  document.querySelectorAll('.agent-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`panel-${agent}`).classList.add('active');
}

// ── Run agent ─────────────────────────────────────────────────────────────────

function runAgent(agent) {
  if (activeES) { activeES.close(); activeES = null; }

  const outputEl = document.getElementById(`output-${agent}`);
  const resultEl = document.getElementById(`result-${agent}`);
  const runBtn   = document.querySelector(`#panel-${agent} .run-btn`);
  const value    = document.getElementById(`samples-${agent}`).value;

  outputEl.innerHTML = '';
  resultEl.innerHTML = '<div class="result-placeholder">Processing…</div>';

  let url;
  if (agent === 'invoice') url = `/api/stream/invoice?sample=${encodeURIComponent(value)}`;
  else if (agent === 'lead') url = `/api/stream/lead?index=${value}`;
  else url = `/api/stream/ticket?index=${value}`;

  runBtn.disabled = true;
  runBtn.textContent = '⟳ Processing…';

  let tokenEl = null;

  activeES = new EventSource(url);

  activeES.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'status') {
      tokenEl = null; // close any open token block
      appendStep(outputEl, msg.message, 'ok');
    }

    else if (msg.type === 'token') {
      if (!tokenEl) {
        const wrap = document.createElement('div');
        wrap.className = 'token-wrapper';
        const lbl = document.createElement('div');
        lbl.className = 'section-label';
        lbl.textContent = 'Model output (streaming):';
        tokenEl = document.createElement('pre');
        tokenEl.className = 'token-stream';
        wrap.appendChild(lbl);
        wrap.appendChild(tokenEl);
        outputEl.appendChild(wrap);
      }
      tokenEl.textContent += msg.text;
      outputEl.scrollTop = outputEl.scrollHeight;
    }

    else if (msg.type === 'pdf_preview') {
      const wrap = document.createElement('div');
      wrap.className = 'pdf-preview';
      wrap.innerHTML = `<div class="section-label">PDF text extracted:</div><pre>${escHtml(msg.text)}</pre>`;
      outputEl.appendChild(wrap);
      outputEl.scrollTop = outputEl.scrollHeight;
    }

    else if (msg.type === 'input') {
      const wrap = document.createElement('div');
      wrap.className = 'input-preview';
      wrap.innerHTML = `<div class="section-label">Input data:</div><pre>${escHtml(JSON.stringify(msg.data, null, 2))}</pre>`;
      outputEl.appendChild(wrap);
      outputEl.scrollTop = outputEl.scrollHeight;
    }

    else if (msg.type === 'result') {
      renderResult(agent, msg.data, resultEl);
    }

    else if (msg.type === 'done') {
      activeES.close(); activeES = null;
      appendStep(outputEl, 'Complete', 'done');
      runBtn.disabled = false;
      runBtn.textContent = '▶ Run Agent';
    }

    else if (msg.type === 'error') {
      appendStep(outputEl, msg.message, 'error');
      activeES.close(); activeES = null;
      runBtn.disabled = false;
      runBtn.textContent = '▶ Run Agent';
    }
  };

  activeES.onerror = () => {
    activeES.close(); activeES = null;
    appendStep(outputEl, 'Connection lost. Check your GROQ_API_KEY and restart the server.', 'error');
    runBtn.disabled = false;
    runBtn.textContent = '▶ Run Agent';
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function appendStep(container, text, kind) {
  const el = document.createElement('div');
  el.className = `step${kind === 'error' ? ' error' : kind === 'done' ? ' done' : ''}`;
  const icon = kind === 'error' ? '✗' : '✓';
  el.innerHTML = `<span class="icon">${icon}</span><span>${escHtml(text)}</span>`;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Result renderers ──────────────────────────────────────────────────────────

function renderResult(agent, data, el) {
  el.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'result-card';
  if (agent === 'invoice')     card.innerHTML = invoiceResult(data);
  else if (agent === 'lead')   card.innerHTML = leadResult(data);
  else                         card.innerHTML = ticketResult(data);
  el.appendChild(card);
}

function invoiceResult(d) {
  const flags = d.flags || [];
  const noFlags = flags.length === 0;

  const flagsHtml = noFlags
    ? '<span class="badge badge-green">No flags raised</span>'
    : flags.map(f =>
        `<div class="flag flag-${f.severity.toLowerCase()}">
          <strong>${f.type}</strong> — ${escHtml(f.message)}
        </div>`
      ).join('');

  const rows = (d.line_items || []).map(item =>
    `<tr>
      <td>${escHtml(item.description)}</td>
      <td class="amount">$${parseFloat(item.amount).toFixed(2)}</td>
    </tr>`
  ).join('');

  const tableHtml = rows
    ? `<table class="line-items-table">
        <thead><tr><th>Description</th><th class="amount">Amount</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><td><strong>Total</strong></td><td class="amount"><strong>$${parseFloat(d.total || 0).toFixed(2)} ${escHtml(d.currency || 'USD')}</strong></td></tr></tfoot>
      </table>`
    : '';

  return `
    <div class="result-title">Extracted Invoice</div>
    <div class="fields-grid">
      <div class="field"><span class="label">Vendor</span><span class="val">${escHtml(d.vendor || '—')}</span></div>
      <div class="field"><span class="label">Invoice #</span><span class="val">${escHtml(d.invoice_number || '—')}</span></div>
      <div class="field"><span class="label">Date</span><span class="val">${escHtml(d.date || '—')}</span></div>
      <div class="field"><span class="label">Due Date</span><span class="val">${escHtml(d.due_date || '—')}</span></div>
      <div class="field"><span class="label">PO Number</span><span class="val">${escHtml(d.po_number || '—')}</span></div>
      <div class="field"><span class="label">Confidence</span><span class="val">${Math.round((d.confidence || 0) * 100)}%</span></div>
    </div>
    ${tableHtml}
    <div class="flags-section">
      <div class="flags-label">Validation Flags</div>
      ${flagsHtml}
    </div>`;
}

function leadResult(d) {
  const man = d.man_score || {};
  const qualClass = d.qualification === 'QUALIFIED' ? 'badge-green' : d.qualification === 'UNQUALIFIED' ? 'badge-yellow' : 'badge-red';

  const dimHtml = ['money', 'authority', 'need'].map(dim => {
    const score = man[dim]?.score || 0;
    const pct   = (score / 10) * 100;
    return `
      <div class="man-dim">
        <div class="dim-header">
          <span class="dim-name">${dim.toUpperCase()}</span>
          <div class="score-bar-wrap">
            <div class="score-track"><div class="score-fill" style="width:${pct}%"></div></div>
            <span class="score-num">${score}/10</span>
          </div>
        </div>
        <div class="dim-reasoning">${escHtml(man[dim]?.reasoning || '')}</div>
      </div>`;
  }).join('');

  return `
    <div class="result-title">Lead Qualification Result</div>
    <div class="badges">
      <span class="badge ${qualClass}">${escHtml(d.qualification)}</span>
      <span class="badge badge-blue">Priority: ${escHtml(d.priority)}</span>
      <span class="badge badge-muted">Score: ${d.total_score}/${d.max_score}</span>
    </div>
    <div class="man-scores">${dimHtml}</div>
    <div class="action-box">
      <div class="action-label">Recommended Action</div>
      <div class="action-text">${escHtml(d.recommended_action || '')}</div>
    </div>
    <div class="action-box">
      <div class="action-label">Suggested Follow-up</div>
      <div class="action-text italic">${escHtml(d.suggested_followup || '')}</div>
    </div>`;
}

function ticketResult(d) {
  const pClass = d.priority === 'P1' ? 'badge-red' : d.priority === 'P2' ? 'badge-yellow' : 'badge-green';
  const escalateBadge = d.escalate
    ? '<span class="badge badge-red">ESCALATE</span>'
    : '<span class="badge badge-muted">No Escalation</span>';

  return `
    <div class="result-title">Triage Result — ${escHtml(d.ticket_id)}</div>
    <div class="badges">
      <span class="badge ${pClass}">${escHtml(d.priority)}</span>
      ${escalateBadge}
      <span class="badge badge-muted">${escHtml(d.category)}</span>
      <span class="badge badge-muted">${Math.round((d.confidence || 0.85) * 100)}% conf.</span>
    </div>
    <div class="fields-grid" style="margin-bottom:12px">
      <div class="field"><span class="label">Subcategory</span><span class="val">${escHtml(d.subcategory || '—')}</span></div>
      ${d.escalation_reason ? `<div class="field"><span class="label">Escalation Reason</span><span class="val" style="color:#fca5a5">${escHtml(d.escalation_reason)}</span></div>` : ''}
    </div>
    <div class="action-box">
      <div class="action-label">Priority Reasoning</div>
      <div class="action-text">${escHtml(d.priority_reasoning || '')}</div>
    </div>
    <div class="action-box">
      <div class="action-label">Draft Response</div>
      <div class="action-text italic">${escHtml(d.suggested_response || '')}</div>
    </div>`;
}
