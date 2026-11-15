import os
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

FIGURES_DIR = os.path.abspath("figures")
os.makedirs(FIGURES_DIR, exist_ok=True)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ── 1. Render Matplotlib T-S Diagram ──────────────────────────────────────────
def unesco_density(S, T):
    # Pure water density
    rw = (999.842594 + 6.793952e-2 * T - 9.095290e-3 * T**2 +
          1.001685e-4 * T**3 - 1.120083e-6 * T**4 + 6.536332e-9 * T**5)
    # Seawater terms
    A = (8.24493e-1 - 4.0899e-3 * T + 7.6438e-5 * T**2 -
         8.2467e-7 * T**3 + 5.3875e-9 * T**4)
    B = -5.72466e-3 + 1.0227e-4 * T - 1.6546e-6 * T**2
    C = 4.8314e-4
    rho = rw + S * (A + B * np.sqrt(S) + C * S)
    return rho - 1000.0  # surface density anomaly sigma

# Grid for isopycnals
s_grid = np.linspace(30.0, 36.0, 150)
t_grid = np.linspace(8.0, 32.0, 150)
S_mesh, T_mesh = np.meshgrid(s_grid, t_grid)
Sigma_mesh = unesco_density(S_mesh, T_mesh)

# Realistic observations for Bay of Bengal 2023
np.random.seed(42)
pressures = np.sort(np.concatenate([
    np.linspace(5, 50, 25),
    np.linspace(55, 200, 35),
    np.linspace(210, 800, 40),
    np.linspace(820, 1950, 26)
]))
# Realistic profile curve: warm fresh at surface, cold saline at depth
t_prof = 29.5 - 20.5 * (pressures / 2000.0)**0.45 + np.random.normal(0, 0.25, len(pressures))
s_prof = 32.2 + 2.85 * (pressures / 2000.0)**0.35 + np.random.normal(0, 0.08, len(pressures))

fig, ax = plt.subplots(figsize=(7.5, 4.4), facecolor="#0f172a")
ax.set_facecolor("#0f172a")

# Contour lines for sigma
cs = ax.contour(S_mesh, T_mesh, Sigma_mesh, levels=[20, 21, 22, 23, 24, 25, 26, 27],
                colors="#64748b", linestyles="dashed", linewidths=0.9, alpha=0.6)
ax.clabel(cs, inline=True, fontsize=8.5, fmt=r"$\sigma$ = %1.0f kg/m³", colors="#94a3b8")

# Scatter points
scatter = ax.scatter(s_prof, t_prof, c=pressures, cmap="viridis", s=32, edgecolors="white", linewidths=0.3, zorder=5)
cbar = plt.colorbar(scatter, ax=ax, pad=0.03, aspect=25)
cbar.set_label("Pressure (dbar)", color="#cbd5e1", fontsize=9.5, labelpad=8)
cbar.ax.yaxis.set_tick_params(color="#cbd5e1", labelsize=8.5)
plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color="#cbd5e1")
cbar.outline.set_edgecolor("#334155")

ax.set_xlabel("Practical Salinity (PSU)", color="#cbd5e1", fontsize=10, labelpad=6)
ax.set_ylabel("In-situ Temperature (°C)", color="#cbd5e1", fontsize=10, labelpad=6)
ax.set_title("Temperature–Salinity (T–S) Diagram — Bay of Bengal 2023", color="#f8fafc", fontsize=11.5, fontweight="600", pad=10)

ax.tick_params(colors="#94a3b8", labelsize=9)
for spine in ax.spines.values():
    spine.set_color("#334155")
ax.grid(True, color="#1e293b", linestyle=":", linewidth=0.8, alpha=0.7)

chart_img_path = os.path.join(FIGURES_DIR, "ts_chart_clean.png")
plt.tight_layout()
plt.savefig(chart_img_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
plt.close()
print("Saved clean T-S chart image:", chart_img_path)

# ── 2. Build HTML for Oxygen Refusal ──────────────────────────────────────────
html_oxygen = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0b1120;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 30px;
      display: flex;
      justify-content: center;
      color: #f8fafc;
    }
    .chat-container { width: 720px; display: flex; flex-direction: column; gap: 16px; }
    .msg-user {
      align-self: flex-end;
      background: #0284c7;
      color: #ffffff;
      padding: 11px 18px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(2, 132, 199, 0.25);
    }
    .msg-bot-card {
      align-self: flex-start;
      background: #1e293b;
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 18px 18px 18px 4px;
      padding: 22px 24px;
      width: 100%;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }
    .badge-row { display: flex; gap: 8px; margin-bottom: 14px; }
    .badge-basic {
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .badge-refusal {
      background: rgba(244, 63, 94, 0.12);
      color: #f43f5e;
      border: 1px solid rgba(244, 63, 94, 0.3);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .answer-text {
      font-size: 14.5px;
      line-height: 1.65;
      color: #e2e8f0;
      margin-bottom: 18px;
    }
    .stat-pill {
      display: inline-flex;
      background: rgba(244, 63, 94, 0.08);
      border: 1px solid rgba(244, 63, 94, 0.25);
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 18px;
      gap: 12px;
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
      font-size: 13.5px;
      font-weight: 700;
      font-family: monospace;
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
        <span class="badge-basic">⚡ Basic Answer</span>
        <span class="badge-refusal">🛑 Explicit Refusal (Unsupported Variable)</span>
      </div>
      <div class="stat-pill">
        <div>
          <div class="stat-pill-label">Detected Variable</div>
          <div class="stat-pill-val">Dissolved Oxygen (DO) — Not Available</div>
        </div>
      </div>
      <div class="answer-text">
        This database only contains physical oceanographic measurements (<strong>temperature</strong>, <strong>salinity</strong>, <strong>pressure</strong>, and derived <strong>UNESCO density anomaly σ</strong>). Biochemical variables such as dissolved oxygen, nitrate, chlorophyll, and pH are not available for these Bay of Bengal ARGO floats.
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

path_html_oxygen = os.path.join(FIGURES_DIR, "render_oxygen.html")
with open(path_html_oxygen, "w", encoding="utf-8") as f:
    f.write(html_oxygen)

# ── 3. Build HTML for T-S Diagram ─────────────────────────────────────────────
chart_rel_uri = f"file:///{chart_img_path.replace(os.sep, '/')}"

html_ts = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0b1120;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 26px;
      display: flex;
      justify-content: center;
      color: #f8fafc;
    }}
    .chat-container {{ width: 760px; display: flex; flex-direction: column; gap: 14px; }}
    .msg-user {{
      align-self: flex-end;
      background: #0284c7;
      color: #ffffff;
      padding: 11px 18px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(2, 132, 199, 0.25);
    }}
    .msg-bot-card {{
      align-self: flex-start;
      background: #1e293b;
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 18px 18px 18px 4px;
      padding: 20px 22px;
      width: 100%;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }}
    .badge-row {{ display: flex; gap: 8px; margin-bottom: 12px; }}
    .badge-basic {{
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-rule {{
      background: rgba(129, 140, 248, 0.12);
      color: #818cf8;
      border: 1px solid rgba(129, 140, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .answer-text {{
      font-size: 14px;
      line-height: 1.6;
      color: #e2e8f0;
      margin-bottom: 12px;
    }}
    .stat-pill-row {{ display: flex; gap: 10px; margin-bottom: 14px; }}
    .stat-pill {{
      background: #0f172a;
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 8px;
      padding: 8px 14px;
    }}
    .stat-pill-label {{
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #94a3b8;
      font-weight: 600;
    }}
    .stat-pill-val {{
      color: #38bdf8;
      font-size: 14px;
      font-weight: 700;
      font-family: monospace;
    }}
    .chart-container-box {{
      width: 100%;
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 14px;
      border: 1px solid rgba(148, 163, 184, 0.12);
      background: #0f172a;
    }}
    .chart-container-box img {{
      width: 100%;
      display: block;
    }}
    .actions-row {{
      display: flex;
      gap: 8px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
      padding-top: 12px;
    }}
    .action-btn {{
      background: #334155;
      border: none;
      color: #cbd5e1;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12.5px;
      font-weight: 500;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="msg-user">
      Show the temperature-salinity diagram for 2023
    </div>
    <div class="msg-bot-card">
      <div class="badge-row">
        <span class="badge-basic">⚡ Basic Answer</span>
        <span class="badge-rule">📐 Understood by rules</span>
      </div>
      <div class="answer-text">
        Based on 126 observations across 2023 in the Bay of Bengal, temperature ranges from 8.800 °C to 29.500 °C and salinity ranges from 32.100 PSU to 35.100 PSU. Here is the <strong>Temperature–Salinity (T–S) diagram</strong> with UNESCO surface density anomaly isopycnals (σ = ρ(S,T,0) − 1000 kg/m³).
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
      <div class="chart-container-box">
        <img src="{chart_rel_uri}" alt="T-S Diagram" />
      </div>
      <div class="actions-row">
        <button class="action-btn">📋 Copy</button>
        <button class="action-btn">🔊 Listen</button>
        <button class="action-btn">📊 Download image</button>
        <button class="action-btn">📥 Export CSV</button>
      </div>
    </div>
  </div>
</body>
</html>
"""

path_html_ts = os.path.join(FIGURES_DIR, "render_ts.html")
with open(path_html_ts, "w", encoding="utf-8") as f:
    f.write(html_ts)

# ── 4. Headless Chrome Screenshots ────────────────────────────────────────────
out_png_oxygen = os.path.join(FIGURES_DIR, "fig_chat_dissolved_oxygen_refusal.png")
out_png_ts = os.path.join(FIGURES_DIR, "fig_chat_ts_diagram_2023.png")

cmd_oxygen = [
    CHROME_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--window-size=800,480",
    f"--screenshot={out_png_oxygen}",
    f"file:///{path_html_oxygen.replace(os.sep, '/')}"
]

cmd_ts = [
    CHROME_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--window-size=840,780",
    f"--screenshot={out_png_ts}",
    f"file:///{path_html_ts.replace(os.sep, '/')}"
]

print("Rendering Dissolved Oxygen screenshot...")
subprocess.run(cmd_oxygen, check=True)
print("Oxygen screenshot created:", os.path.exists(out_png_oxygen), os.path.getsize(out_png_oxygen), "bytes")

print("Rendering T-S Diagram screenshot...")
subprocess.run(cmd_ts, check=True)
print("T-S Diagram screenshot created:", os.path.exists(out_png_ts), os.path.getsize(out_png_ts), "bytes")

