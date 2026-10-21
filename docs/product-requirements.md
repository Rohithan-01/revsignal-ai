<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RevSignal Dashboard</title>
    <style>
      :root {
        --bg: #f5f7fb;
        --panel: #ffffff;
        --card: #eef3ff;
        --primary: #1d4ed8;
        --text: #132238;
        --muted: #5c6f8a;
        --good: #10b981;
        --warn: #f59e0b;
        --bad: #ef4444;
        --border: #d9e3f0;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Arial, sans-serif;
        background: var(--bg);
        color: var(--text);
      }
      .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
      .topbar {
        display: flex; justify-content: space-between; align-items: center;
        padding: 18px 0 24px 0;
      }
      .brand { font-size: 1.8rem; font-weight: 700; }
      .toolbar { display: flex; gap: 12px; align-items: center; }
      button, input {
        padding: 10px 14px; border-radius: 10px; border: 1px solid var(--border);
        font-size: 1rem;
      }
      button {
        background: var(--primary); color: white; border: none; cursor: pointer;
      }
      .cards {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;
        margin-bottom: 24px;
      }
      .card {
        background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 18px;
        box-shadow: 0 10px 18px rgba(17,24,39,0.04);
      }
      .label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; }
      .value { font-size: 2rem; font-weight: 700; margin-top: 8px; }
      .section {
        background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 20px;
        margin-bottom: 24px;
      }
      .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
      table { width: 100%; border-collapse: collapse; }
      th, td { text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--border); }
      th { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; }
      .risk-pill {
        display: inline-block; padding: 6px 10px; border-radius: 999px; font-weight: 700; font-size: 0.8rem;
      }
      .LOW { background: rgba(16,185,129,0.12); color: var(--good); }
      .MEDIUM { background: rgba(245,158,11,0.12); color: var(--warn); }
      .HIGH { background: rgba(239,68,68,0.12); color: var(--bad); }
      .detail-panel {
        display: grid; grid-template-columns: 2fr 1fr; gap: 24px;
      }
      .detail-box {
        border: 1px solid var(--border); border-radius: 12px; background: var(--card); padding: 16px;
      }
      .muted { color: var(--muted); }
      ul { padding-left: 18px; }
      form { display: flex; gap: 10px; flex-wrap: wrap; }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="topbar">
        <div class="brand">RevSignal</div>
        <div class="toolbar">
          <form id="uploadForm">
            <input type="file" id="csvFile" accept=".csv" />
            <button type="submit">Upload CSV</button>
          </form>
        </div>
      </div>

      <div id="metrics" class="cards"></div>

      <div class="section">
        <div class="section-header">
          <h2>Open pipeline</h2>
        </div>
        <div id="dealTableContainer"></div>
      </div>

      <div class="section">
        <div class="section-header">
          <h2>Deal detail</h2>
        </div>
        <div id="detailPanel" class="detail-panel"></div>
      </div>
    </div>

    <script>
      const metricsContainer = document.getElementById('metrics');
      const tableContainer = document.getElementById('dealTableContainer');
      const detailPanel = document.getElementById('detailPanel');

      function currency(value) {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
      }

      function renderMetrics(data) {
        const cards = [
          { label: 'Total open pipeline', value: currency(data.total_open_pipeline_value) },
          { label: 'High-risk revenue', value: currency(data.revenue_high_risk) },
          { label: 'High-risk deals', value: data.high_risk_deals },
          { label: 'Deals needing attention', value: data.deals_needing_attention }
        ];

        metricsContainer.innerHTML = cards.map(card => `
          <div class="card">
            <div class="label">${card.label}</div>
            <div class="value">${card.value}</div>
          </div>
        `).join('');
      }

      function renderTable(deals) {
        if (!deals.length) {
          tableContainer.innerHTML = '<p class="muted">No deals available. Upload a CSV to begin.</p>';
          return;
        }

        tableContainer.innerHTML = `
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Stage</th>
                <th>Value</th>
                <th>Risk</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${deals.map(deal => `
                <tr>
                  <td><button style="background:transparent;color:#1d4ed8;padding:0;border:none;cursor:pointer" data-deal-id="${deal.deal_id}">${deal.account_name}</button></td>
                  <td>${deal.stage}</td>
                  <td>${currency(deal.deal_value)}</td>
                  <td><span class="risk-pill ${deal.risk_level}">${deal.risk_level}</span> (${deal.risk_score})</td>
                  <td>${deal.recommended_action}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;

        document.querySelectorAll('[data-deal-id]').forEach(btn => {
          btn.addEventListener('click', () => fetchDeal(btn.dataset.dealId));
        });
      }

      function renderDetail(deal) {
        detailPanel.innerHTML = `
          <div class="detail-box">
            <h3>${deal.account_name}</h3>
            <p><strong>Deal ID:</strong> ${deal.deal_id}</p>
            <p><strong>Stage:</strong> ${deal.stage}</p>
            <p><strong>Status:</strong> ${deal.status}</p>
            <p><strong>Deal value:</strong> ${currency(deal.deal_value)}</p>
            <p><strong>Expected close:</strong> ${deal.expected_close_date || 'N/A'}</p>
            <p><strong>Last activity:</strong> ${deal.last_activity_date || 'N/A'}</p>
            <p><strong>Stakeholders:</strong> ${deal.stakeholder_count ?? 'N/A'}</p>
          </div>
          <div class="detail-box">
            <p><strong>Risk score:</strong> <span class="risk-pill ${deal.risk_level}">${deal.risk_level}</span> ${deal.risk_score}</p>
            <h4>Evidence</h4>
            <ul>${(deal.risk_reasons || []).map(item => `<li>${item}</li>`).join('')}</ul>
            <h4>Recommended action</h4>
            <p>${deal.recommended_action}</p>
          </div>
        `;
      }

      async function fetchDeals() {
        const response = await fetch('/api/deals');
        const deals = await response.json();
        renderTable(deals);
        if (deals[0]) fetchDeal(deals[0].deal_id);
      }

      async function fetchMetrics() {
        const response = await fetch('/api/metrics');
        const data = await response.json();
        renderMetrics(data);
        renderTable(data.top_deals || []);
        if ((data.top_deals || [])[0]) fetchDeal(data.top_deals[0].deal_id);
      }

      async function fetchDeal(dealId) {
        const response = await fetch(`/api/deals/${dealId}`);
        if (!response.ok) return;
        const deal = await response.json();
        renderDetail(deal);
      }

      document.getElementById('uploadForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const fileInput = document.getElementById('csvFile');
        if (!fileInput.files.length) return;

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        const response = await fetch('/api/deals/upload', {
          method: 'POST',
          body: formData
        });

        if (response.ok) {
          fetchMetrics();
          fetchDeals();
        } else {
          const error = await response.json();
          alert(error.detail || 'Upload failed');
        }
      });

      fetchMetrics();
      fetchDeals();
    </script>
  </body>
</html>
