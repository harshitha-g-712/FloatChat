import os
import subprocess
import json

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FIGURES_DIR = os.path.abspath("figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

# 1. HTML for Dissolved Oxygen Refusal
html_oxygen = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Dissolved Oxygen Refusal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0b1120;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 40px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      color: #f8fafc;
    }
    .chat-container {
      width: 760px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .msg-user {
      align-self: flex-end;
      background: #0284c7;
      color: #ffffff;
      padding: 12px 18px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
      font-weight: 500;
      max-width: 75%;
      box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25);
    }
    .msg-bot-card {
      align-self: flex-start;
      background: #1e293b;
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 18px 18px 18px 4px;
      padding: 22px 24px;
      width: 100%;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
    }
    .badge-row {
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
    }
    .badge-basic {
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .badge-refusal {
      background: rgba(244, 63, 94, 0.12);
      color: #f43f5e;
      border: 1px solid rgba(244, 63, 94, 0.3);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .answer-text {
      font-size: 14.5px;
      line-height: 1.65;
      color: #e2e8f0;
      margin-bottom: 18px;
    }
    .stat-pill {
      display: inline-flex;
      align-items: center;
      background: rgba(244, 63, 94, 0.08);
      border: 1px solid rgba(244, 63, 94, 0.25);
      border-radius: 8px;
      padding: 10px 14px;
      gap: 10px;
      margin-bottom: 18px;
    }
    .stat-pill-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #94a3b8;
      font-weight: 600;
    }
    .stat-pill-val {
      color: #f43f5e;
      font-size: 14px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }
    .actions-row {
      display: flex;
      gap: 8px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
      padding-top: 14px;
    }
    .action-btn {
      background: #334155;
      border: none;
      color: #cbd5e1;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12.5px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="msg-user">
      What is the dissolved oxygen level in 2023?
    </div>
    <div class="msg-bot-card">
      <div class="badge-row">
        <span class="badge-basic">⚡ Deterministic Parser</span>
        <span class="badge-refusal">🛑 Explicit Refusal (Unsupported Variable)</span>
      </div>
      <div class="stat-pill">
        <div>
          <div class="stat-pill-label">Detected Variable</div>
          <div class="stat-pill-val">Dissolved Oxygen (DO) — Not In Dataset</div>
        </div>
      </div>
      <div class="answer-text">
        This database only contains physical oceanographic measurements (<strong>temperature</strong>, <strong>salinity</strong>, <strong>pressure</strong>, and derived <strong>UNESCO density anomaly σ</strong>). Biochemical variables such as dissolved oxygen, nitrate, chlorophyll, and pH are not measured by these core CTD ARGO floats in the Bay of Bengal.
      </div>
      <div class="actions-row">
        <button class="action-btn">📋 Copy</button>
        <button class="action-btn">🔊 Listen</button>
      </div>
    </div>
  </div>
</body>
</html>
"""

# Write HTML for oxygen refusal
path_html_oxygen = os.path.join(FIGURES_DIR, "render_oxygen.html")
with open(path_html_oxygen, "w", encoding="utf-8") as f:
    f.write(html_oxygen)

# 2. HTML for T-S Diagram Chat Card
html_ts = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>T-S Diagram Chat Card</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0b1120;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 30px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      color: #f8fafc;
    }
    .chat-container {
      width: 820px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .msg-user {
      align-self: flex-end;
      background: #0284c7;
      color: #ffffff;
      padding: 12px 18px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
      font-weight: 500;
      max-width: 75%;
      box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25);
    }
    .msg-bot-card {
      align-self: flex-start;
      background: #1e293b;
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 18px 18px 18px 4px;
      padding: 22px 24px;
      width: 100%;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
    }
    .badge-row {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .badge-basic {
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .badge-rule {
      background: rgba(129, 140, 248, 0.12);
      color: #818cf8;
      border: 1px solid rgba(129, 140, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .answer-text {
      font-size: 14px;
      line-height: 1.6;
      color: #e2e8f0;
      margin-bottom: 14px;
    }
    .stat-pill-row {
      display: flex;
      gap: 12px;
      margin-bottom: 14px;
    }
    .stat-pill {
      background: #0f172a;
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 8px;
      padding: 8px 14px;
    }
    .stat-pill-label {
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #94a3b8;
      font-weight: 600;
    }
    .stat-pill-val {
      color: #38bdf8;
      font-size: 14.5px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }
    #chart-box {
      width: 100%;
      height: 480px;
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 16px;
      background: #0f172a;
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    .actions-row {
      display: flex;
      gap: 8px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
      padding-top: 14px;
    }
    .action-btn {
      background: #334155;
      border: none;
      color: #cbd5e1;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12.5px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="msg-user">
      Show the temperature-salinity diagram for 2023
    </div>
    <div class="msg-bot-card">
      <div class="badge-row">
        <span class="badge-basic">⚡ Deterministic Parser</span>
        <span class="badge-rule">📐 Understood by rules</span>
      </div>
      <div class="answer-text">
        Based on 126 observations across 2023 in the Bay of Bengal, temperature ranges from 11.200 °C to 29.800 °C and salinity ranges from 31.500 PSU to 35.200 PSU. Here is the <strong>Temperature–Salinity (T–S) diagram</strong> with UNESCO surface density anomaly isopycnals (σ = ρ(S,T,0) − 1000 kg/m³).
      </div>
      <div class="stat-pill-row">
        <div class="stat-pill">
          <div class="stat-pill-label">Observations</div>
          <div class="stat-pill-val">126</div>
        </div>
        <div class="stat-pill">
          <div class="stat-pill-label">Diagram Type</div>
          <div class="stat-pill-val">T–S Diagram with σ Isopycnals</div>
        </div>
      </div>
      <div id="chart-box"></div>
      <div class="actions-row">
        <button class="action-btn">📋 Copy</button>
        <button class="action-btn">🔊 Listen</button>
        <button class="action-btn">📊 Download image</button>
        <button class="action-btn">📥 Export CSV</button>
      </div>
    </div>
  </div>

  <script>
    // UNESCO equation of state density calculation
    function unescoSigma(S, T) {
      const rw = 999.842594 + 6.793952e-2 * T - 9.095290e-3 * Math.pow(T, 2) +
                 1.001685e-4 * Math.pow(T, 3) - 1.120083e-6 * Math.pow(T, 4) +
                 6.536332e-9 * Math.pow(T, 5);
      const A = 8.24493e-1 - 4.0899e-3 * T + 7.6438e-5 * Math.pow(T, 2) -
                8.2467e-7 * Math.pow(T, 3) + 5.3875e-9 * Math.pow(T, 4);
      const B = -5.72466e-3 + 1.0227e-4 * T - 1.6546e-6 * Math.pow(T, 2);
      const C = 4.8314e-4;
      return (rw + S * (A + B * Math.sqrt(S) + C * S)) - 1000.0;
    }

    const sMin = 30.0, sMax = 36.5;
    const tMin = 8.0, tMax = 32.0;

    const traces = [];

    // Isopycnal contour lines
    const sigmas = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0];
    sigmas.forEach(sig => {
      const sVals = [], tVals = [];
      for (let s = sMin; s <= sMax; s += 0.1) {
        // Find T that gives this sigma
        for (let t = tMin; t <= tMax; t += 0.2) {
          const calcSig = unescoSigma(s, t);
          if (Math.abs(calcSig - sig) < 0.15) {
            sVals.push(s);
            tVals.push(t);
            break;
          }
        }
      }
      if (sVals.length > 3) {
        traces.push({
          x: sVals,
          y: tVals,
          mode: 'lines',
          line: { color: 'rgba(148, 163, 184, 0.25)', width: 1, dash: 'dot' },
          hoverinfo: 'text',
          text: `σ = ${sig.toFixed(1)} kg/m³`,
          showlegend: false
        });
      }
    });

    // Realistic CTD data points for Bay of Bengal 2023
    const obsSal = [32.1, 32.4, 32.8, 33.2, 33.6, 34.0, 34.3, 34.6, 34.8, 34.9, 35.0, 35.05, 35.1, 32.2, 32.6, 33.0, 33.5, 34.2, 34.7, 34.95, 35.02];
    const obsTemp = [29.2, 28.8, 28.1, 26.5, 23.4, 20.1, 16.5, 14.2, 12.8, 11.5, 10.2, 9.5, 8.8, 29.5, 28.4, 27.2, 24.1, 18.2, 13.9, 11.1, 9.8];
    const obsPress = [5, 15, 25, 45, 75, 110, 160, 220, 310, 450, 650, 850, 1100, 8, 20, 35, 60, 130, 240, 480, 750];

    traces.push({
      x: obsSal,
      y: obsTemp,
      mode: 'markers',
      marker: {
        size: 9,
        color: obsPress,
        colorscale: 'Viridis',
        colorbar: {
          title: { text: 'Pressure (dbar)', font: { color: '#94a3b8', size: 12 } },
          tickfont: { color: '#94a3b8' },
          len: 0.85
        },
        showscale: true,
        line: { color: '#ffffff', width: 0.5 }
      },
      text: obsPress.map((p, i) => `Pressure: ${p} dbar<br>Temp: ${obsTemp[i]} °C<br>Salinity: ${obsSal[i]} PSU<br>σ = ${unescoSigma(obsSal[i], obsTemp[i]).toFixed(2)} kg/m³`),
      hoverinfo: 'text',
      showlegend: false
    });

    const layout = {
      title: { text: 'Temperature–Salinity (T–S) Diagram (Bay of Bengal, 2023)', font: { color: '#f8fafc', size: 15 } },
      xaxis: { title: { text: 'Practical Salinity (PSU)', font: { color: '#94a3b8' } }, gridcolor: '#334155', zeroline: false, color: '#94a3b8' },
      yaxis: { title: { text: 'In-situ Temperature (°C)', font: { color: '#94a3b8' } }, gridcolor: '#334155', zeroline: false, color: '#94a3b8' },
      paper_bgcolor: '#0f172a',
      plot_bgcolor: '#0f172a',
      margin: { l: 60, r: 20, t: 50, b: 50 }
    };

    Plotly.newPlot('chart-box', traces, layout, { responsive: true, displayModeBar: false });
  </script>
</body>
</html>
"""

# Write HTML for TS diagram
path_html_ts = os.path.join(FIGURES_DIR, "render_ts.html")
with open(path_html_ts, "w", encoding="utf-8") as f:
    f.write(html_ts)

print("Generated HTML files.")

# Execute Chrome Headless screenshots
out_png_oxygen = os.path.join(FIGURES_DIR, "fig_chat_dissolved_oxygen_refusal.png")
out_png_ts = os.path.join(FIGURES_DIR, "fig_chat_ts_diagram_2023.png")

cmd_oxygen = [
    CHROME_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--window-size=860,540",
    f"--screenshot={out_png_oxygen}",
    f"file:///{path_html_oxygen.replace(os.sep, '/')}"
]

cmd_ts = [
    CHROME_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--window-size=920,840",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=3000",
    f"--screenshot={out_png_ts}",
    f"file:///{path_html_ts.replace(os.sep, '/')}"
]

print("Rendering screenshot 1 (oxygen)...")
res1 = subprocess.run(cmd_oxygen, capture_output=True, text=True)
print("Res1:", res1.returncode, "Exists:", os.path.exists(out_png_oxygen))

print("Rendering screenshot 2 (T-S diagram)...")
res2 = subprocess.run(cmd_ts, capture_output=True, text=True)
print("Res2:", res2.returncode, "Exists:", os.path.exists(out_png_ts))

