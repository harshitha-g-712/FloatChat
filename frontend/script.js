/**
 * FloatChat – Frontend JavaScript
 * ================================
 * Full-featured interactive oceanographic discovery UI:
 *  - Rules-First & Gemini AI answering with Answer Mode badges
 *  - Dedicated Data Discover Tab with coverage cards, float table & trajectory modal
 *  - Plotly.js charts (depth profiles, maps, distributions, timeseries, trajectories)
 *  - CSV export, speech recognition voice search, and token auth
 *  - Relative API URL fallback
 */

"use strict";

// ── Configuration (Relative API URLs with disk fallback) ──────────────────────
const API_BASE = (window.location.origin && window.location.origin.startsWith("http"))
  ? ""
  : "http://127.0.0.1:8000";

const ENDPOINTS = {
  chat:          `${API_BASE}/api/chat`,
  export:        `${API_BASE}/api/export`,
  reset:         `${API_BASE}/api/reset`,
  health:        `${API_BASE}/api/health`,
  register:      `${API_BASE}/api/register`,
  login:         `${API_BASE}/api/login`,
  logout:        `${API_BASE}/api/logout`,
  me:            `${API_BASE}/api/me`,
  conversations: `${API_BASE}/api/conversations`,
  searchConv:    `${API_BASE}/api/conversations/search`,
  floats:        `${API_BASE}/api/floats`,
  mapPoints:     `${API_BASE}/api/map/points`,
  coverage:      `${API_BASE}/api/coverage`,
  shared:        `${API_BASE}/api/shared`,
  diveProfile:   (platform) => `${API_BASE}/api/floats/${encodeURIComponent(platform)}/dive-profile`,
  updateUsername: `${API_BASE}/api/profile/username`,
  changePassword: `${API_BASE}/api/profile/password`,
  logoutAll:      `${API_BASE}/api/profile/logout-all`,
  forgotPassword: `${API_BASE}/api/forgot-password`,
  resetPassword:  `${API_BASE}/api/reset-password`,
};

// ── State ─────────────────────────────────────────────────────────────────────
let authToken = localStorage.getItem("floatchat-token") || null;
let currentUser = null;
let conversationId = localStorage.getItem("floatchat-conv-id") || crypto.randomUUID();
let isBusy = false;
let loadSeq = 0;   // guards loadConversation against out-of-order responses
let listSeq = 0;   // guards loadConversations against out-of-order responses
const CONV_PAGE = 100;
let convLimit = CONV_PAGE;   // grows by CONV_PAGE each time "Load more" is pressed
let lastMessageData = null;
let activeTab = "chat";
let allFloats = [];

// ── DOM References ────────────────────────────────────────────────────────────
const authScreen       = document.getElementById("auth-screen");
const appShell         = document.getElementById("app-shell");
const loginForm        = document.getElementById("login-form");
const registerForm     = document.getElementById("register-form");
const loginError       = document.getElementById("login-error");
const registerError    = document.getElementById("register-error");
const showRegisterLink = document.getElementById("show-register");
const showLoginLink    = document.getElementById("show-login");
const showForgotLink   = document.getElementById("show-forgot");
const forgotForm       = document.getElementById("forgot-form");
const forgotStep1      = document.getElementById("forgot-step-1");
const forgotStep2      = document.getElementById("forgot-step-2");
const forgotEmailInput = document.getElementById("forgot-email");
const forgotSendBtn    = document.getElementById("forgot-send-btn");
const forgotNotice     = document.getElementById("forgot-notice");
const forgotError      = document.getElementById("forgot-error");
const forgotCodeInput  = document.getElementById("forgot-code");
const forgotNewPwInput = document.getElementById("forgot-new-password");
const forgotResetBtn   = document.getElementById("forgot-reset-btn");
const resetNotice      = document.getElementById("reset-notice");
const resetError       = document.getElementById("reset-error");
const forgotBackToLogin = document.getElementById("forgot-back-to-login");

// Session Expiry & Warning
const sessionWarningBanner = document.getElementById("session-warning-banner");
const sessionWarningText   = document.getElementById("session-warning-text");
const sessionRefreshBtn    = document.getElementById("session-refresh-btn");
const sessionDismissBtn    = document.getElementById("session-dismiss-btn");

// Voice Visualizer
const voiceVisualizer      = document.getElementById("voice-visualizer");
const voiceStatusText      = document.getElementById("voice-status-text");
const voiceCancelBtn       = document.getElementById("voice-cancel-btn");

// Conversation Filtering
const convFilterRow        = document.getElementById("conv-filter-row");
let convActiveFilter       = "all";

// Float Report & Plotly Export
const floatReportBtn       = document.getElementById("float-report-btn");
const floatExportChartBtn  = document.getElementById("float-export-chart-btn");

const tabChatBtn       = document.getElementById("tab-chat-btn");
const tabDiscoverBtn   = document.getElementById("tab-discover-btn");
const chatFeed         = document.getElementById("chat-feed");
const discoverFeed     = document.getElementById("discover-feed");
const askForm          = document.getElementById("ask-form");
const currentViewTitle = document.getElementById("current-view-title");

const questionInput    = document.getElementById("question-input");
const sendBtn          = document.getElementById("send-btn");
const messagesEl       = document.getElementById("messages");
const welcomeCard      = document.getElementById("welcome-card");
const statusBar        = document.getElementById("status-bar");
const exportBtn        = document.getElementById("export-btn");
const healthBtn        = document.getElementById("health-btn");
const healthModal      = document.getElementById("health-modal");
const healthContent    = document.getElementById("health-content");
const healthClose      = document.getElementById("health-modal-close");
const newChatBtn       = document.getElementById("new-chat-btn");
const sidebarToggle    = document.getElementById("sidebar-toggle");
const sidebar          = document.getElementById("sidebar");
const sidebarResizer   = document.getElementById("sidebar-resizer");
const userMenuBtn      = document.getElementById("user-menu-btn");
const userInitial      = document.getElementById("user-initial");
const userDropdown     = document.getElementById("user-dropdown");
const dropdownUsername = document.getElementById("dropdown-username");
const dropdownEmail    = document.getElementById("dropdown-email");
const dropdownAvatar   = document.getElementById("dropdown-avatar");
const logoutBtn        = document.getElementById("logout-btn");
const profileBtn       = document.getElementById("profile-btn");

// Profile Modal Elements
const profileModal         = document.getElementById("profile-modal");
const profileModalClose    = document.getElementById("profile-modal-close");
const profileAvatarLarge   = document.getElementById("profile-avatar-large");
const profileDisplayName   = document.getElementById("profile-display-name");
const profileDisplayEmail  = document.getElementById("profile-display-email");
const profileTotalChats    = document.getElementById("profile-total-chats");
const profileMemberSince   = document.getElementById("profile-member-since");
const profileSessionStatus = document.getElementById("profile-session-status");
const profileEditUsername  = document.getElementById("profile-edit-username");
const profileSaveUsername  = document.getElementById("profile-save-username");
const profileStaticEmail   = document.getElementById("profile-static-email");
const profileCurrentPw     = document.getElementById("profile-current-pw");
const profileNewPw         = document.getElementById("profile-new-pw");
const profileConfirmPw     = document.getElementById("profile-confirm-pw");
const profilePwError       = document.getElementById("profile-pw-error");
const profilePwSuccess     = document.getElementById("profile-pw-success");
const profileChangePwBtn   = document.getElementById("profile-change-pw-btn");
const profileLogoutAllBtn  = document.getElementById("profile-logout-all-btn");

// Register Form Enhancement Elements
const regPasswordInput     = document.getElementById("register-password");
const regConfirmPassword   = document.getElementById("register-confirm-password");
const pwStrengthContainer  = document.getElementById("password-strength");
const pwStrengthFill       = document.getElementById("password-strength-fill");
const pwStrengthText       = document.getElementById("password-strength-text");
const pwMatchHint          = document.getElementById("pw-match-hint");
const searchInput      = document.getElementById("search-input");
const convList         = document.getElementById("conversation-list");

// Discover Elements
const floatSearchInput   = document.getElementById("float-search-input");
const floatsTableBody    = document.getElementById("floats-table-body");
const exportFloatsCsvBtn = document.getElementById("export-floats-csv");
const refreshDiscoverBtn = document.getElementById("refresh-discover-btn");
const dbEmptyState       = document.getElementById("db-empty-state");
const floatModal         = document.getElementById("float-modal");
const floatModalTitle    = document.getElementById("float-modal-title");
const floatModalStats    = document.getElementById("float-modal-stats");
const floatModalClose    = document.getElementById("float-modal-close");

// Simulator Elements
const tabSimulatorBtn    = document.getElementById("tab-simulator-btn");
const diveSimTopBtn      = document.getElementById("dive-sim-top-btn");
const simulatorFeed      = document.getElementById("simulator-feed");
const simFloatSelect     = document.getElementById("sim-float-select");
const simLoadBtn         = document.getElementById("sim-load-btn");
const simPlayBtn         = document.getElementById("sim-play-btn");
const simResetBtn        = document.getElementById("sim-reset-btn");
const simSpeedBtns       = document.querySelectorAll(".sim-speed-btn");
const simDepthSlider     = document.getElementById("sim-depth-slider");
const simOceanCanvas     = document.getElementById("sim-ocean-canvas");
const simPhaseBadge      = document.getElementById("sim-phase-badge");
const simZoneTag         = document.getElementById("sim-zone-tag");
const simHudDepth        = document.getElementById("sim-hud-depth");
const simHudTemp         = document.getElementById("sim-hud-temp");
const simHudSal          = document.getElementById("sim-hud-sal");
const simHudSpeed        = document.getElementById("sim-hud-speed");
const simPhysMld         = document.getElementById("sim-phys-mld");
const simPhysThermocline = document.getElementById("sim-phys-thermocline");
const simPhysSofar       = document.getElementById("sim-phys-sofar");
const simPlotlyChart     = document.getElementById("sim-plotly-chart");

// Map Elements
const tabMapBtn        = document.getElementById("tab-map-btn");
const mapFeed          = document.getElementById("map-feed");
const mapFloatFilter   = document.getElementById("map-float-filter");
const mapYearFilter    = document.getElementById("map-year-filter");
const mapBasemapSelect = document.getElementById("map-basemap-select");
const mapToggleLines   = document.getElementById("map-toggle-lines");
const mapResetBtn      = document.getElementById("map-reset-btn");
const mapStatsText     = document.getElementById("map-stats-text");
const mapFloatCard     = document.getElementById("map-float-card");
const mapCardPlatform  = document.getElementById("map-card-platform");
const mapCardBody      = document.getElementById("map-card-body");
const mapCardClose     = document.getElementById("map-card-close");

// FastAPI returns `detail` as a string, or as a list of validation errors (422).
function apiErrorText(data, fallback) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const msg = d[0] && (d[0].msg || d[0].message);
    if (typeof msg === "string") return msg.replace(/^Value error, /, "");
  }
  return fallback;
}

// ── Auth Helpers ──────────────────────────────────────────────────────────────
function authHeaders() {
  return authToken
    ? { "Authorization": `Bearer ${authToken}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}


// Shared Plotly helpers keep chart failures visible instead of leaving blank panels.
function showChartState(target, message, isError = false) {
  const el = typeof target === "string" ? document.getElementById(target) : target;
  if (!el) return;
  if (window.Plotly && el.data) {
    try { Plotly.purge(el); } catch (_) {}
  }
  el.innerHTML = `<div class="chart-state${isError ? " is-error" : ""}" role="status">${escapeHtml(message)}</div>`;
}

async function renderPlotlyChart(target, traces, layout = {}, config = {}) {
  const el = typeof target === "string" ? document.getElementById(target) : target;
  if (!el) throw new Error("Chart container was not found.");
  if (!window.Plotly || typeof Plotly.newPlot !== "function") {
    showChartState(el, "Charts are unavailable because the Plotly library did not load.", true);
    return false;
  }
  if (!Array.isArray(traces) || traces.length === 0) {
    showChartState(el, "No chart data is available for this selection.");
    return false;
  }
  try {
    el.innerHTML = "";
    await Plotly.newPlot(el, traces, {
      margin: { l: 50, r: 20, t: 40, b: 50 },
      ...layout,
      // Force the existing dark palette even when a backend chart supplies light defaults.
      paper_bgcolor: "#1e293b", plot_bgcolor: "#0f172a",
      font: { ...(layout.font || {}), family: "'Inter', sans-serif", color: "#94a3b8" },
    }, { responsive: true, displayModeBar: false, ...config });
    return true;
  } catch (err) {
    showChartState(el, `Chart could not be rendered: ${err?.message || "unknown error"}`, true);
    return false;
  }
}

// Shown when the saved session could not be verified for a non-auth reason.
// The token is kept; the user can retry without signing in again.
function showSessionRetry(reason) {
  authScreen.hidden = true;
  appShell.hidden = false;
  showStatus(`${reason} Retrying in 5 seconds...`, true);
  clearTimeout(showSessionRetry._t);
  showSessionRetry._t = setTimeout(checkAuth, 5000);
}

async function checkAuth() {
  if (!authToken) { showAuth(); return; }
  try {
    const resp = await fetch(ENDPOINTS.me, { headers: authHeaders() });
    // Only an explicit "not authorised" ends the session. A server error or a network
    // blip must not delete the saved token and log the user out.
    if (resp.status === 401 || resp.status === 403) { showAuth(); return; }
    if (!resp.ok) { showSessionRetry(`Server error (${resp.status}).`); return; }
    const data = await resp.json();
    currentUser = data.user;
    showApp();
  } catch (_) {
    showSessionRetry("Cannot reach the server.");
  }
}

// Wipe everything that belongs to the previous session so the next person to use
// this browser never sees someone else's chats, titles or search text.
function resetUiState() {
  stopSpeaking();
  loadSeq++;                       // cancel any in-flight history request
  listSeq++;
  convLimit = CONV_PAGE;
  if (messagesEl) messagesEl.innerHTML = "";
  if (convList) convList.replaceChildren();
  if (searchInput) searchInput.value = "";
  if (questionInput) { questionInput.value = ""; questionInput.style.height = "auto"; }
  if (welcomeCard) { welcomeCard.style.display = ""; welcomeCard.style.opacity = "1"; }
  lastMessageData = null;
  conversationId = crypto.randomUUID();
  localStorage.setItem("floatchat-conv-id", conversationId);
  clearStatus();
  sidebar?.classList.remove("open");
  if (typeof userDropdown !== "undefined" && userDropdown) userDropdown.hidden = true;
}

function showAuth() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem("floatchat-token");
  resetUiState();
  authScreen.hidden = false;
  appShell.hidden = true;
}

function showApp() {
  clearStatus();
  authScreen.hidden = true;
  appShell.hidden = false;
  const initial = (currentUser?.username || "U")[0].toUpperCase();
  if (userInitial) userInitial.textContent = initial;
  if (dropdownAvatar) dropdownAvatar.textContent = initial;
  if (dropdownUsername) dropdownUsername.textContent = currentUser?.username || "User";
  if (dropdownEmail) dropdownEmail.textContent = currentUser?.email || "";
  checkSessionExpiry();
  loadConversations();
  loadDiscoveryData();
  healthPing();
  // After a page refresh, show the conversation the next question will be added to.
  loadConversation(conversationId, { silent: true });
}

function checkSessionExpiry() {
  if (!sessionWarningBanner || !sessionWarningText) return;
  if (!currentUser || currentUser.session_remaining_seconds == null) {
    sessionWarningBanner.hidden = true;
    return;
  }
  const rem = currentUser.session_remaining_seconds;
  // If less than 24 hours (86400 seconds) remaining
  if (rem > 0 && rem < 86400) {
    const hours = Math.max(1, Math.round(rem / 3600));
    sessionWarningText.textContent = `Your session will expire in approximately ${hours} hour${hours > 1 ? 's' : ''}.`;
    sessionWarningBanner.hidden = false;
  } else {
    sessionWarningBanner.hidden = true;
  }
}

sessionDismissBtn?.addEventListener("click", () => {
  if (sessionWarningBanner) sessionWarningBanner.hidden = true;
});

sessionRefreshBtn?.addEventListener("click", async () => {
  if (sessionRefreshBtn) { sessionRefreshBtn.disabled = true; sessionRefreshBtn.textContent = "Extending..."; }
  try {
    const resp = await fetch(ENDPOINTS.me, { headers: authHeaders() });
    if (resp.ok) {
      const data = await resp.json();
      currentUser = data.user;
      if (sessionWarningBanner) sessionWarningBanner.hidden = true;
      showStatus("Session extended successfully ✓");
      setTimeout(clearStatus, 3000);
    }
  } catch (_) {
    showStatus("Could not extend session", true);
  } finally {
    if (sessionRefreshBtn) { sessionRefreshBtn.disabled = false; sessionRefreshBtn.textContent = "Extend Session"; }
  }
});

// ── Auth Forms & Password Enhancements ─────────────────────────────────────────

// Password visibility toggles
document.querySelectorAll(".auth-toggle-pw").forEach(btn => {
  btn.addEventListener("click", () => {
    const targetId = btn.getAttribute("data-target");
    const input = document.getElementById(targetId);
    if (!input) return;
    const isPw = input.type === "password";
    input.type = isPw ? "text" : "password";
    btn.textContent = isPw ? "🙈" : "👁️";
    btn.classList.toggle("active", isPw);
  });
});

// Password strength indicator
function assessPasswordStrength(pw) {
  if (!pw) return { score: 0, level: "weak", label: "" };
  let score = 0;
  if (pw.length >= 10) score += 1;
  if (pw.length >= 14) score += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1;
  if (/\d/.test(pw)) score += 1;
  if (/[^a-zA-Z0-9]/.test(pw)) score += 1;

  if (score <= 1) return { score: 1, level: "weak", label: "Weak (minimum 10 characters required)" };
  if (score === 2) return { score: 2, level: "fair", label: "Fair — add numbers & uppercase" };
  if (score === 3 || score === 4) return { score: 3, level: "good", label: "Good password" };
  return { score: 4, level: "strong", label: "Strong password ✓" };
}

regPasswordInput?.addEventListener("input", () => {
  const pw = regPasswordInput.value;
  if (!pw) {
    if (pwStrengthContainer) pwStrengthContainer.hidden = true;
    return;
  }
  if (pwStrengthContainer) pwStrengthContainer.hidden = false;
  const { level, label } = assessPasswordStrength(pw);
  if (pwStrengthFill) pwStrengthFill.setAttribute("data-level", level);
  if (pwStrengthText) {
    pwStrengthText.setAttribute("data-level", level);
    pwStrengthText.textContent = label;
  }
  checkPwMatch();
});

function checkPwMatch() {
  if (!regConfirmPassword || !regPasswordInput || !pwMatchHint) return;
  const pw1 = regPasswordInput.value;
  const pw2 = regConfirmPassword.value;
  if (!pw2) {
    pwMatchHint.hidden = true;
    return;
  }
  pwMatchHint.hidden = false;
  if (pw1 === pw2) {
    pwMatchHint.textContent = "Passwords match ✓";
    pwMatchHint.className = "auth-field-hint auth-pw-match match";
  } else {
    pwMatchHint.textContent = "Passwords do not match";
    pwMatchHint.className = "auth-field-hint auth-pw-match no-match";
  }
}

regConfirmPassword?.addEventListener("input", checkPwMatch);

showRegisterLink?.addEventListener("click", (e) => {
  e.preventDefault();
  loginForm.hidden = true;
  registerForm.hidden = false;
  loginError.hidden = true;
  registerError.hidden = true;
});
showLoginLink?.addEventListener("click", (e) => {
  e.preventDefault();
  registerForm.hidden = true;
  loginForm.hidden = false;
  loginError.hidden = true;
  registerError.hidden = true;
});

// ── Forgot Password Handlers ──────────────────────────────────────────────────
showForgotLink?.addEventListener("click", (e) => {
  e.preventDefault();
  loginForm.hidden = true;
  registerForm.hidden = true;
  forgotForm.hidden = false;
  forgotStep1.hidden = false;
  forgotStep2.hidden = true;
  if (forgotNotice) forgotNotice.hidden = true;
  if (forgotError) forgotError.hidden = true;
  if (forgotEmailInput && document.getElementById("login-email")) {
    forgotEmailInput.value = document.getElementById("login-email").value;
  }
});

forgotBackToLogin?.addEventListener("click", (e) => {
  e.preventDefault();
  forgotForm.hidden = true;
  loginForm.hidden = false;
});

forgotSendBtn?.addEventListener("click", async () => {
  if (forgotError) forgotError.hidden = true;
  if (forgotNotice) forgotNotice.hidden = true;
  const email = forgotEmailInput ? forgotEmailInput.value.trim() : "";
  if (!email || !email.includes("@")) {
    if (forgotError) { forgotError.textContent = "Please enter a valid email address."; forgotError.hidden = false; }
    return;
  }
  const btnText = forgotSendBtn.querySelector(".auth-btn-text");
  const btnLoader = forgotSendBtn.querySelector(".auth-btn-loader");
  if (forgotSendBtn) forgotSendBtn.disabled = true;
  if (btnText) btnText.textContent = "Sending code...";
  if (btnLoader) btnLoader.hidden = false;

  try {
    const resp = await fetch(ENDPOINTS.forgotPassword, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (forgotError) { forgotError.textContent = apiErrorText(data, "Request failed"); forgotError.hidden = false; }
      return;
    }
    // Switch to step 2
    forgotStep1.hidden = true;
    forgotStep2.hidden = false;
    if (data.reset_code && forgotCodeInput) {
      forgotCodeInput.value = data.reset_code;
      const codeHint = document.getElementById("forgot-code-hint");
      if (codeHint) codeHint.textContent = `Offline reset code: ${data.reset_code} (auto-filled)`;
    }
    if (resetNotice) {
      resetNotice.textContent = data.message || "Verification code issued. Enter your code and new password.";
      resetNotice.hidden = false;
    }
  } catch (err) {
    if (forgotError) { forgotError.textContent = "Cannot reach server. Please try again."; forgotError.hidden = false; }
  } finally {
    if (forgotSendBtn) forgotSendBtn.disabled = false;
    if (btnText) btnText.textContent = "Get Verification Code";
    if (btnLoader) btnLoader.hidden = true;
  }
});

forgotResetBtn?.addEventListener("click", async () => {
  if (resetError) resetError.hidden = true;
  if (resetNotice) resetNotice.hidden = true;
  const email = forgotEmailInput ? forgotEmailInput.value.trim() : "";
  const reset_code = forgotCodeInput ? forgotCodeInput.value.trim() : "";
  const new_password = forgotNewPwInput ? forgotNewPwInput.value : "";

  if (!reset_code) {
    if (resetError) { resetError.textContent = "Please enter the verification code."; resetError.hidden = false; }
    return;
  }
  if (!new_password || new_password.length < 10) {
    if (resetError) { resetError.textContent = "New password must be at least 10 characters."; resetError.hidden = false; }
    return;
  }

  const btnText = forgotResetBtn.querySelector(".auth-btn-text");
  const btnLoader = forgotResetBtn.querySelector(".auth-btn-loader");
  if (forgotResetBtn) forgotResetBtn.disabled = true;
  if (btnText) btnText.textContent = "Updating password...";
  if (btnLoader) btnLoader.hidden = false;

  try {
    const resp = await fetch(ENDPOINTS.resetPassword, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, reset_code, new_password }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (resetError) { resetError.textContent = apiErrorText(data, "Reset failed"); resetError.hidden = false; }
      return;
    }
    forgotForm.hidden = true;
    loginForm.hidden = false;
    const loginNotice = document.getElementById("login-notice");
    if (loginNotice) {
      loginNotice.textContent = "Password updated successfully ✓ Please sign in.";
      loginNotice.hidden = false;
    }
    if (document.getElementById("login-email")) {
      document.getElementById("login-email").value = email;
    }
  } catch (err) {
    if (resetError) { resetError.textContent = "Cannot reach server. Please try again."; resetError.hidden = false; }
  } finally {
    if (forgotResetBtn) forgotResetBtn.disabled = false;
    if (btnText) btnText.textContent = "Reset Password";
    if (btnLoader) btnLoader.hidden = true;
  }
});

loginForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.hidden = true;
  const loginNotice = document.getElementById("login-notice");
  if (loginNotice) loginNotice.hidden = true;
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const btn = document.getElementById("login-submit-btn");
  const btnText = btn?.querySelector(".auth-btn-text");
  const btnLoader = btn?.querySelector(".auth-btn-loader");

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = "Signing in...";
  if (btnLoader) btnLoader.hidden = false;

  try {
    const resp = await fetch(ENDPOINTS.login, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await resp.json();
    if (!resp.ok) { loginError.textContent = apiErrorText(data, "Login failed"); loginError.hidden = false; return; }
    authToken = data.token;
    currentUser = data.user;
    localStorage.setItem("floatchat-token", authToken);
    resetUiState();
    showApp();
  } catch (err) {
    loginError.textContent = "Cannot reach server. Is backend running?";
    loginError.hidden = false;
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = "Sign In";
    if (btnLoader) btnLoader.hidden = true;
  }
});

registerForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  registerError.hidden = true;
  const username = document.getElementById("register-username").value.trim();
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value;
  const confirmPassword = regConfirmPassword ? regConfirmPassword.value : password;

  if (password !== confirmPassword) {
    registerError.textContent = "Passwords do not match. Please verify and try again.";
    registerError.hidden = false;
    return;
  }
  if (password.length < 10) {
    registerError.textContent = "Password must be at least 10 characters long.";
    registerError.hidden = false;
    return;
  }

  const btn = document.getElementById("register-submit-btn");
  const btnText = btn?.querySelector(".auth-btn-text");
  const btnLoader = btn?.querySelector(".auth-btn-loader");

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = "Creating account...";
  if (btnLoader) btnLoader.hidden = false;

  try {
    const resp = await fetch(ENDPOINTS.register, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });
    const data = await resp.json();
    if (!resp.ok) { registerError.textContent = apiErrorText(data, "Registration failed"); registerError.hidden = false; return; }
    // The server gives the same answer whether or not the email already had an account, so we
    // cannot sign the user in here: send them to the sign-in form instead.
    registerForm.reset();
    if (pwStrengthContainer) pwStrengthContainer.hidden = true;
    if (pwMatchHint) pwMatchHint.hidden = true;
    registerForm.hidden = true;
    loginForm.hidden = false;
    document.getElementById("login-email").value = email.trim().toLowerCase();
    const notice = document.getElementById("login-notice");
    if (notice) { notice.textContent = (data && data.message) || "Account request received. Please sign in."; notice.hidden = false; }
  } catch (err) {
    registerError.textContent = "Cannot reach server. Is backend running?";
    registerError.hidden = false;
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = "Create Account";
    if (btnLoader) btnLoader.hidden = true;
  }
});

// ── Profile Management Modal ──────────────────────────────────────────────────
function openProfileModal() {
  if (!currentUser) return;
  const initial = (currentUser.username || "U")[0].toUpperCase();
  if (profileAvatarLarge) profileAvatarLarge.textContent = initial;
  if (profileDisplayName) profileDisplayName.textContent = currentUser.username || "User";
  if (profileDisplayEmail) profileDisplayEmail.textContent = currentUser.email || "";
  if (profileStaticEmail) profileStaticEmail.textContent = currentUser.email || "";
  if (profileEditUsername) profileEditUsername.value = currentUser.username || "";
  
  if (profileTotalChats) {
    const chatCount = currentUser.conversation_count != null
      ? currentUser.conversation_count
      : (document.querySelectorAll("#conversation-list .conv-item").length || 0);
    profileTotalChats.textContent = chatCount;
  }
  if (profileMemberSince) {
    if (currentUser.created_at) {
      try {
        const dt = new Date(currentUser.created_at);
        profileMemberSince.textContent = dt.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
      } catch (_) {
        profileMemberSince.textContent = "Recent";
      }
    } else {
      profileMemberSince.textContent = "Recent";
    }
  }
  if (profileSessionStatus) profileSessionStatus.textContent = "Active";

  if (profileCurrentPw) profileCurrentPw.value = "";
  if (profileNewPw) profileNewPw.value = "";
  if (profileConfirmPw) profileConfirmPw.value = "";
  if (profilePwError) profilePwError.hidden = true;
  if (profilePwSuccess) profilePwSuccess.hidden = true;
  if (profileSaveUsername) { profileSaveUsername.textContent = "Save"; profileSaveUsername.disabled = false; }

  if (userDropdown) userDropdown.hidden = true;
  if (profileModal) profileModal.hidden = false;
}

profileBtn?.addEventListener("click", openProfileModal);
profileModalClose?.addEventListener("click", () => { if (profileModal) profileModal.hidden = true; });
profileModal?.addEventListener("click", (e) => { if (e.target === profileModal) profileModal.hidden = true; });

// Save Username
profileSaveUsername?.addEventListener("click", async () => {
  if (!profileEditUsername) return;
  const newName = profileEditUsername.value.trim();
  if (!newName || newName === currentUser?.username) return;
  profileSaveUsername.disabled = true;
  profileSaveUsername.textContent = "Saving...";
  try {
    const resp = await fetch(ENDPOINTS.updateUsername, {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify({ username: newName }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(apiErrorText(data, "Failed to update username"));
      return;
    }
    currentUser.username = data.username;
    const initial = data.username[0].toUpperCase();
    if (userInitial) userInitial.textContent = initial;
    if (dropdownAvatar) dropdownAvatar.textContent = initial;
    if (dropdownUsername) dropdownUsername.textContent = data.username;
    if (profileAvatarLarge) profileAvatarLarge.textContent = initial;
    if (profileDisplayName) profileDisplayName.textContent = data.username;
    profileSaveUsername.textContent = "Saved ✓";
  } catch (err) {
    alert("Could not update username: Network error");
  } finally {
    profileSaveUsername.disabled = false;
    setTimeout(() => { if (profileSaveUsername) profileSaveUsername.textContent = "Save"; }, 1800);
  }
});

// Update Password
profileChangePwBtn?.addEventListener("click", async () => {
  if (profilePwError) profilePwError.hidden = true;
  if (profilePwSuccess) profilePwSuccess.hidden = true;
  const oldPw = profileCurrentPw ? profileCurrentPw.value : "";
  const newPw = profileNewPw ? profileNewPw.value : "";
  const confPw = profileConfirmPw ? profileConfirmPw.value : "";

  if (!oldPw) {
    if (profilePwError) { profilePwError.textContent = "Please enter your current password."; profilePwError.hidden = false; }
    return;
  }
  if (!newPw || newPw.length < 10) {
    if (profilePwError) { profilePwError.textContent = "New password must be at least 10 characters."; profilePwError.hidden = false; }
    return;
  }
  if (newPw !== confPw) {
    if (profilePwError) { profilePwError.textContent = "New passwords do not match."; profilePwError.hidden = false; }
    return;
  }

  profileChangePwBtn.disabled = true;
  profileChangePwBtn.textContent = "Updating...";
  try {
    const resp = await fetch(ENDPOINTS.changePassword, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (profilePwError) {
        profilePwError.textContent = apiErrorText(data, "Failed to change password");
        profilePwError.hidden = false;
      }
      return;
    }
    if (profilePwSuccess) {
      profilePwSuccess.textContent = "Password changed successfully ✓";
      profilePwSuccess.hidden = false;
    }
    if (profileCurrentPw) profileCurrentPw.value = "";
    if (profileNewPw) profileNewPw.value = "";
    if (profileConfirmPw) profileConfirmPw.value = "";
  } catch (err) {
    if (profilePwError) { profilePwError.textContent = "Network error. Please try again."; profilePwError.hidden = false; }
  } finally {
    profileChangePwBtn.disabled = false;
    profileChangePwBtn.textContent = "🔑 Update Password";
  }
});

// Sign Out All Sessions
profileLogoutAllBtn?.addEventListener("click", async () => {
  if (!confirm("Are you sure you want to sign out from all devices and sessions?")) return;
  try {
    await fetch(ENDPOINTS.logoutAll, { method: "POST", headers: authHeaders() });
  } catch (_) {}
  if (profileModal) profileModal.hidden = true;
  showAuth();
});

// ── Tab Switching ─────────────────────────────────────────────────────────────
tabChatBtn?.addEventListener("click", () => switchTab("chat"));
tabMapBtn?.addEventListener("click", () => switchTab("map"));
tabDiscoverBtn?.addEventListener("click", () => switchTab("discover"));
tabSimulatorBtn?.addEventListener("click", () => switchTab("simulator"));
diveSimTopBtn?.addEventListener("click", () => switchTab("simulator"));

function switchTab(tab) {
  activeTab = tab;
  tabChatBtn?.classList.toggle("active", tab === "chat");
  tabMapBtn?.classList.toggle("active", tab === "map");
  tabDiscoverBtn?.classList.toggle("active", tab === "discover");
  tabSimulatorBtn?.classList.toggle("active", tab === "simulator");

  if (tab === "chat") {
    if (chatFeed) chatFeed.style.display = "";
    if (mapFeed) mapFeed.style.display = "none";
    if (discoverFeed) discoverFeed.style.display = "none";
    if (simulatorFeed) simulatorFeed.style.display = "none";
    if (askForm) askForm.style.display = "";
    if (currentViewTitle) currentViewTitle.textContent = "ARGO Ocean Data Chat";
  } else if (tab === "map") {
    if (chatFeed) chatFeed.style.display = "none";
    if (mapFeed) mapFeed.style.display = "flex";
    if (discoverFeed) discoverFeed.style.display = "none";
    if (simulatorFeed) simulatorFeed.style.display = "none";
    if (askForm) askForm.style.display = "none";
    if (currentViewTitle) currentViewTitle.textContent = "Interactive Geospatial Ocean Map";
    initOceanMap();
  } else if (tab === "discover") {
    if (chatFeed) chatFeed.style.display = "none";
    if (mapFeed) mapFeed.style.display = "none";
    if (discoverFeed) discoverFeed.style.display = "block";
    if (simulatorFeed) simulatorFeed.style.display = "none";
    if (askForm) askForm.style.display = "none";
    if (currentViewTitle) currentViewTitle.textContent = "ARGO Float Discovery";
    loadDiscoveryData();
  } else if (tab === "simulator") {
    if (chatFeed) chatFeed.style.display = "none";
    if (mapFeed) mapFeed.style.display = "none";
    if (discoverFeed) discoverFeed.style.display = "none";
    if (simulatorFeed) simulatorFeed.style.display = "block";
    if (askForm) askForm.style.display = "none";
    if (currentViewTitle) currentViewTitle.textContent = "ARGO 4D Mission Simulator & Sonar";
    initSimulator();
  }
}

// ── Discovery Data Loader ─────────────────────────────────────────────────────
async function loadDiscoveryData() {
  try {
    // 1. Fetch coverage
    const covResp = await fetch(ENDPOINTS.coverage, { headers: authHeaders() });
    if (covResp.ok) {
      const cov = await covResp.json();
      document.getElementById("metric-profiles").textContent = (cov.total_profiles || 0).toLocaleString();
      document.getElementById("metric-floats").textContent = (cov.total_floats || 0).toLocaleString();
      document.getElementById("metric-measurements").textContent = (cov.total_measurements || 0).toLocaleString();
      
      const d1 = (cov.date_start || "").substring(0, 10);
      const d2 = (cov.date_end || "").substring(0, 10);
      document.getElementById("metric-dates").textContent = d1 && d2 ? `${d1} to ${d2}` : "N/A";

      if (cov.total_profiles === 0) {
        dbEmptyState.style.display = "block";
      } else {
        dbEmptyState.style.display = "none";
      }

      // Render coverage chart
      if (cov.profiles_by_month && Object.keys(cov.profiles_by_month).length > 0) {
        const months = Object.keys(cov.profiles_by_month).sort();
        const counts = months.map(m => Number(cov.profiles_by_month[m]) || 0);
        await renderPlotlyChart("coverage-chart-div", [{
          x: months, y: counts, type: "bar", marker: { color: "#818cf8" },
          hovertemplate: "Month: %{x}<br>Profiles: %{y}<extra></extra>"
        }], {
          title: { text: "Monthly Profile Distribution", font: { color: "#f8fafc", size: 14 } },
          margin: { l: 45, r: 20, t: 40, b: 40 },
          xaxis: { gridcolor: "#334155" }, yaxis: { gridcolor: "#334155" }
        });
      } else {
        showChartState("coverage-chart-div", "No monthly profile data is available yet.");
      }
    } else {
      showChartState("coverage-chart-div", `Coverage request failed (${covResp.status}). Try refreshing.`, true);
    }

    // 2. Fetch floats table
    const floatResp = await fetch(ENDPOINTS.floats, { headers: authHeaders() });
    if (floatResp.ok) {
      const data = await floatResp.json();
      allFloats = Array.isArray(data.floats) ? data.floats : [];
      renderFloatsTable(allFloats);
    } else {
      floatsTableBody.innerHTML = `<tr><td colspan="7" class="table-state-error">Could not load floats (HTTP ${floatResp.status}). Please refresh and try again.</td></tr>`;
    }
  } catch (err) {
    console.error("Discovery load error:", err);
    if (floatsTableBody) floatsTableBody.innerHTML = '<tr><td colspan="7" class="table-state-error">Could not connect to the backend. Check that FloatChat is running, then refresh.</td></tr>';
    showChartState("coverage-chart-div", "Discovery data could not be loaded. Check the backend connection.", true);
  }
}

function renderFloatsTable(floats) {
  if (!floats || floats.length === 0) {
    floatsTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding: 20px;">No ARGO floats found.</td></tr>';
    return;
  }

  floatsTableBody.innerHTML = floats.map(f => {
    const box = f.bounding_box || {};
    const latStr = box.min_lat != null ? `${box.min_lat.toFixed(1)}° to ${box.max_lat.toFixed(1)}°N` : "—";
    const lonStr = box.min_lon != null ? `${box.min_lon.toFixed(1)}° to ${box.max_lon.toFixed(1)}°E` : "—";
    const d1 = (f.first_date || "").substring(0, 10);
    const d2 = (f.last_date || "").substring(0, 10);

    return `
      <tr data-platform="${escapeHtml(f.platform)}">
        <td><strong>${escapeHtml(f.platform)}</strong></td>
        <td>${f.profile_count}</td>
        <td>${d1}</td>
        <td>${d2}</td>
        <td>${latStr}, ${lonStr}</td>
        <td>${f.avg_max_depth ? f.avg_max_depth.toFixed(1) + " dbar" : "—"}</td>
        <td>
          <button class="view-float-btn" data-platform="${escapeHtml(f.platform)}">Explore</button>
          <button class="action-btn sim-float-table-btn" data-platform="${escapeHtml(f.platform)}" style="margin-left: 4px; padding: 3px 8px; font-size: 11px;" title="Open in 4D Dive Simulator">🤿 Sim</button>
        </td>
      </tr>
    `;
  }).join("");

  document.querySelectorAll(".view-float-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openFloatDetail(btn.dataset.platform);
    });
  });

  document.querySelectorAll(".sim-float-table-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openSimulatorForFloat(btn.dataset.platform);
    });
  });

  document.querySelectorAll("#floats-table-body tr").forEach(row => {
    row.addEventListener("click", () => {
      const plat = row.dataset.platform;
      if (plat) openFloatDetail(plat);
    });
  });
}

floatSearchInput?.addEventListener("input", () => {
  const q = floatSearchInput.value.trim().toLowerCase();
  if (!q) {
    renderFloatsTable(allFloats);
    return;
  }
  const filtered = allFloats.filter(f => f.platform.toLowerCase().includes(q));
  renderFloatsTable(filtered);
});

refreshDiscoverBtn?.addEventListener("click", loadDiscoveryData);

exportFloatsCsvBtn?.addEventListener("click", () => {
  if (!allFloats.length) return;
  let csv = "platform,profile_count,first_date,last_date,min_lat,max_lat,min_lon,max_lon,avg_max_depth\n";
  allFloats.forEach(f => {
    const b = f.bounding_box || {};
    csv += `"${f.platform}",${f.profile_count},"${f.first_date || ''}","${f.last_date || ''}",${b.min_lat || ''},${b.max_lat || ''},${b.min_lon || ''},${b.max_lon || ''},${f.avg_max_depth || ''}\n`;
  });
  downloadBlob(csv, "floatchat_all_floats.csv", "text/csv");
});

// ── Float Detail Modal ────────────────────────────────────────────────────────
async function openFloatDetail(platform) {
  if (!platform) return;
  floatModalTitle.textContent = `ARGO Float Platform ${platform}`;
  floatModalStats.innerHTML = "<p>Loading float metadata and trajectory...</p>";
  floatModal.hidden = false;
  showChartState("float-trajectory-chart", "Loading trajectory…");

  try {
    const resp = await fetch(`${ENDPOINTS.floats}/${platform}`, { headers: authHeaders() });
    if (!resp.ok) {
      floatModalStats.innerHTML = "<p>Could not load float details.</p>";
      return;
    }
    const data = await resp.json();
    const s = data.summary;
    const traj = data.trajectory || [];

    const d1 = (s.first_date || "").substring(0, 10);
    const d2 = (s.last_date || "").substring(0, 10);
    const lastPos = s.last_position ? `(${s.last_position.lat.toFixed(2)}°N, ${s.last_position.lon.toFixed(2)}°E)` : "N/A";

    floatModalStats.innerHTML = `
      <div class="modal-stat-card"><span class="lbl">Profiles</span><span class="val">${s.profile_count}</span></div>
      <div class="modal-stat-card"><span class="lbl">Active Period</span><span class="val">${d1} – ${d2}</span></div>
      <div class="modal-stat-card"><span class="lbl">Last Position</span><span class="val">${lastPos}</span></div>
      <div class="modal-stat-card"><span class="lbl">Avg Max Depth</span><span class="val">${s.avg_max_depth != null ? escapeHtml(s.avg_max_depth) : "—"}${s.avg_max_depth != null ? " dbar" : ""}</span></div>
      <div class="modal-stat-card" style="cursor: pointer; background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.4);" id="modal-launch-sim-btn"><span class="lbl">🤿 4D Dive Simulator</span><span class="val" style="font-size: 13px; color: #38bdf8;">Launch Mission ➔</span></div>
    `;

    document.getElementById("modal-launch-sim-btn")?.addEventListener("click", () => {
      floatModal.hidden = true;
      openSimulatorForFloat(platform);
    });

    // Render trajectory map only from valid coordinate pairs.
    const validTraj = traj.filter(p => p.lat != null && p.lon != null && p.lat !== "" && p.lon !== "" && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon)));
    if (validTraj.length > 0) {
      const lats = validTraj.map(p => Number(p.lat));
      const lons = validTraj.map(p => Number(p.lon));
      const labels = validTraj.map(p => `Profile: ${p.profile_id ?? "—"}<br>${(p.timestamp || "").substring(0, 10)}`);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      const minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const center = { lat: (minLat + maxLat) / 2, lon: (minLon + maxLon) / 2 };
      const spread = Math.max(maxLat - minLat, maxLon - minLon);
      const scale = spread > 0 ? Math.max(1, Math.min(20, 25 / spread)) : 5;
      await renderPlotlyChart("float-trajectory-chart", [{
        type: "scattergeo", lat: lats, lon: lons, mode: "lines+markers",
        line: { width: 3, color: "#38bdf8" }, marker: { size: 6, color: "#f43f5e" },
        text: labels, hoverinfo: "text+lat+lon"
      }], {
        title: { text: `Trajectory for Float ${platform}`, font: { color: "#f8fafc", size: 13 } },
        geo: {
          center, projection: { type: "natural earth", scale },
          showland: true, landcolor: "#0f172a", showocean: true, oceancolor: "#1e293b",
          showcountries: true, countrycolor: "#475569", coastlinecolor: "#475569",
          lataxis: { gridcolor: "#334155" }, lonaxis: { gridcolor: "#334155" }
        }, margin: { l: 0, r: 0, t: 35, b: 0 }
      });
    } else {
      showChartState("float-trajectory-chart", "No valid trajectory coordinates are available for this float.");
    }
  } catch (e) {
    floatModalStats.innerHTML = `<p class="table-state-error">Could not load float details: ${escapeHtml(e.message || "request failed")}</p>`;
    showChartState("float-trajectory-chart", "The trajectory map could not be loaded. Please try again.", true);
  }
}
floatModalClose?.addEventListener("click", () => floatModal.hidden = true);
floatModal?.addEventListener("click", (e) => { if (e.target === floatModal) floatModal.hidden = true; });

floatReportBtn?.addEventListener("click", () => {
  window.print();
});

floatExportChartBtn?.addEventListener("click", () => {
  const chartEl = document.getElementById("float-trajectory-chart");
  if (chartEl && window.Plotly) {
    const titleText = (floatModalTitle?.textContent || "float_trajectory").replace(/[^\w-]/g, "_");
    Plotly.downloadImage(chartEl, {
      format: "png",
      width: 900,
      height: 500,
      filename: `argolens_${titleText}`
    });
  }
});

// ── User Dropdown & Menu ──────────────────────────────────────────────────────
userMenuBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  userDropdown.hidden = !userDropdown.hidden;
});
document.addEventListener("click", (e) => {
  if (!userDropdown.contains(e.target) && e.target !== userMenuBtn) userDropdown.hidden = true;
});
logoutBtn?.addEventListener("click", async () => {
  try { await fetch(ENDPOINTS.logout, { method: "POST", headers: authHeaders() }); } catch (_) {}
  showAuth();
});

// ── Conversation Management ──────────────────────────────────────────────────
function setConvListMessage(text) {
  if (!convList) return;
  convList.replaceChildren();
  const el = document.createElement("div");
  el.className = "conv-empty";
  el.textContent = text;
  convList.appendChild(el);
}

async function loadConversations(query = "") {
  if (!convList || !authToken) return;
  const seq = ++listSeq;
  // Keep the existing items visible while a refresh is in progress.
  try {
    const url = query
      ? `${ENDPOINTS.searchConv}?q=${encodeURIComponent(query)}&limit=${convLimit}`
      : `${ENDPOINTS.conversations}?limit=${convLimit}`;
    const resp = await fetch(url, { headers: authHeaders(), cache: "no-store" });
    if (seq !== listSeq) return;                      // a newer request superseded this one
    if (resp.status === 401 || resp.status === 403) {
      showAuth();                                      // expired/invalid token: back to sign-in
      return;
    }
    if (!resp.ok) {
      console.error("FloatChat history request failed:", resp.status, await resp.text().catch(() => ""));
      setConvListMessage("Could not load history. Refresh to retry.");
      return;
    }
    const data = await resp.json();
    if (seq !== listSeq) return;
    const conversations = Array.isArray(data) ? data : (Array.isArray(data.conversations) ? data.conversations : []);
    renderConversationList(conversations);
  } catch (err) {
    if (seq !== listSeq) return;
    console.error("FloatChat history load failed:", err);
    setConvListMessage("Could not connect to load history.");
  }
}

function renderConversationList(conversations) {
  if (!convList) return;
  convList.replaceChildren();
  if (!Array.isArray(conversations) || conversations.length === 0) {
    setConvListMessage(searchInput?.value.trim() ? "No matching conversations" : "No conversations yet");
    return;
  }
  conversations.forEach(c => {
    if (!c || !c.id) return;
    const label = c.title || "New Chat";

    // A row is a <div> holding two sibling buttons (open + delete); nesting a
    // button-like element inside a <button> is invalid HTML and breaks keyboard use.
    const row = document.createElement("div");
    row.className = "conv-item" + (c.id === conversationId ? " active" : "");
    row.dataset.convId = c.id;

    const open = document.createElement("button");
    open.type = "button";
    open.className = "conv-item-title";
    open.textContent = label;
    open.title = label;
    if (c.id === conversationId) open.setAttribute("aria-current", "true");
    open.addEventListener("click", () => loadConversation(c.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "conv-item-delete";
    del.title = "Delete conversation";
    del.setAttribute("aria-label", `Delete ${label}`);
    del.textContent = "×";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return;
      try {
        const resp = await fetch(`${ENDPOINTS.conversations}/${encodeURIComponent(c.id)}`, { method: "DELETE", headers: authHeaders() });
        if (resp.status === 401 || resp.status === 403) { showAuth(); return; }
        if (!resp.ok && resp.status !== 404) throw new Error(`Delete failed (${resp.status})`);
        if (c.id === conversationId) startNewChat();
        await loadConversations(searchInput?.value.trim() || "");
      } catch (err) {
        console.error("Could not delete conversation:", err);
        showStatus("Could not delete that conversation. Please try again.", true);
      }
    });

    // Clicking the empty part of the row also opens the chat.
    row.addEventListener("click", (e) => {
      if (!e.target.closest("button")) loadConversation(c.id);
    });
    row.append(open, del);
    convList.appendChild(row);
  });

  applyConversationFilter();

  // A full page means there may be more: offer to fetch the next batch.
  if (conversations.length >= convLimit) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "conv-more";
    more.textContent = "Load more";
    more.addEventListener("click", () => {
      convLimit += CONV_PAGE;
      loadConversations(searchInput?.value.trim() || "");
    });
    convList.appendChild(more);
  }
}

function applyConversationFilter() {
  if (!convList) return;
  const items = convList.querySelectorAll(".conv-item");
  items.forEach((item, index) => {
    const title = item.querySelector(".conv-item-title")?.textContent || "";
    let match = true;
    if (convActiveFilter === "recent") {
      match = index < 15;
    } else if (convActiveFilter === "named") {
      match = title.trim() !== "New Chat";
    }
    item.style.display = match ? "" : "none";
  });
}

convFilterRow?.addEventListener("click", (e) => {
  const pill = e.target.closest(".conv-filter-pill");
  if (!pill) return;
  convFilterRow.querySelectorAll(".conv-filter-pill").forEach(p => p.classList.remove("active"));
  pill.classList.add("active");
  convActiveFilter = pill.getAttribute("data-filter") || "all";
  applyConversationFilter();
});

// Opens a saved conversation. Messages are fetched BEFORE the current view is touched,
// so a failed request leaves the screen as it was instead of blanking it.
// opts.silent: used on page load; no error banner and an empty/missing chat is left alone.
async function loadConversation(convId, opts = {}) {
  const silent = !!opts.silent;
  if (!convId || !authToken) return;
  stopSpeaking();
  if (isBusy && !silent) {
    showStatus("Please wait for the current answer to finish before switching chats.", true);
    return;
  }
  const seq = ++loadSeq;
  if (!silent) { clearStatus(); sidebar.classList.remove("open"); }

  let messages;
  try {
    const resp = await fetch(`${ENDPOINTS.conversations}/${encodeURIComponent(convId)}/messages`, { headers: authHeaders(), cache: "no-store" });
    if (seq !== loadSeq) return;                       // user clicked something else meanwhile
    if (resp.status === 401 || resp.status === 403) { showAuth(); return; }
    if (!resp.ok) {
      if (!silent) showStatus(resp.status === 404 ? "That conversation no longer exists." : `Could not open that conversation (${resp.status}).`, true);
      if (!silent && resp.status === 404) loadConversations(searchInput?.value.trim() || "");
      return;
    }
    const data = await resp.json();
    if (seq !== loadSeq) return;
    messages = Array.isArray(data.messages) ? data.messages : [];
  } catch (err) {
    if (seq !== loadSeq) return;
    console.error("FloatChat could not load conversation:", err);
    if (!silent) showStatus("Could not connect to load that conversation.", true);
    return;
  }

  if (silent && messages.length === 0) return;        // brand-new chat: keep the welcome card

  conversationId = convId;
  localStorage.setItem("floatchat-conv-id", convId);
  messagesEl.innerHTML = "";
  welcomeCard.style.display = "none";
  switchTab("chat");

  if (messages.length === 0) {
    renderBotText("This conversation has no saved messages.");
  }
  messages.forEach(msg => {
    try {
      if (msg.role === "user") {
        renderUser(msg.content);
      } else if (msg.role === "assistant" && msg.response_data && typeof msg.response_data === "object") {
        renderBot(msg.response_data, "");
      } else if (msg.role === "assistant") {
        renderBotText(msg.content);
      }
    } catch (err) {
      console.error("Could not render a saved message:", err);
      renderBotText(msg.content || "");               // fall back to plain text for this message
    }
  });
  scrollToBottom();
  loadConversations(searchInput?.value.trim() || "");
}

let searchTimer = null;
searchInput?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  convLimit = CONV_PAGE;
  searchTimer = setTimeout(() => loadConversations(searchInput.value.trim()), 300);
});

function scrollToBottom() {
  requestAnimationFrame(() => { chatFeed.scrollTop = chatFeed.scrollHeight; });
}

function setBusy(busy) {
  isBusy = busy;
  sendBtn.disabled = busy;
  questionInput.disabled = busy;
}

function showStatus(msg, isError = false) {
  statusBar.textContent = msg;
  statusBar.className = "status-bar" + (isError ? " error-bar" : "");
}
function clearStatus() { statusBar.className = "status-bar hidden"; }

questionInput?.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + "px";
});

questionInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!isBusy) askForm.dispatchEvent(new Event("submit"));
  }
});

sidebarToggle?.addEventListener("click", () => sidebar.classList.toggle("open"));
document.addEventListener("click", (e) => {
  if (sidebar && sidebarToggle && !sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
    sidebar.classList.remove("open");
  }
});

// ── Draggable Sidebar Navigation Resizer ──────────────────────────────────────
function initSidebarResizer() {
  if (!sidebarResizer || !sidebar) return;

  const DEFAULT_WIDTH = 260;
  const MIN_WIDTH = 190;
  const MAX_WIDTH = Math.min(560, Math.floor(window.innerWidth * 0.5));

  // Load saved preference
  const savedWidth = parseInt(localStorage.getItem("floatchat_sidebar_w"), 10);
  if (!isNaN(savedWidth) && savedWidth >= MIN_WIDTH && savedWidth <= 600) {
    applySidebarWidth(savedWidth, false);
  }

  function applySidebarWidth(w, triggerResize = true) {
    const clamped = Math.max(MIN_WIDTH, Math.min(w, Math.min(580, Math.floor(window.innerWidth * 0.55))));
    document.documentElement.style.setProperty("--sidebar-w", `${clamped}px`);
    sidebar.style.width = `${clamped}px`;
    sidebar.style.minWidth = `${clamped}px`;
    if (triggerResize) {
      if (typeof oceanLeafletMap !== "undefined" && oceanLeafletMap) {
        oceanLeafletMap.invalidateSize();
      }
      if (typeof Plotly !== "undefined" && Plotly.Plots) {
        document.querySelectorAll(".plotly-graph-div").forEach((el) => {
          try { Plotly.Plots.resize(el); } catch (_) {}
        });
      }
    }
  }

  let isDragging = false;
  let startX = 0;
  let startW = DEFAULT_WIDTH;

  function onDragStart(e) {
    if (e.type === "mousedown" && e.button !== 0) return;
    isDragging = true;
    startX = e.type.startsWith("touch") ? e.touches[0].clientX : e.clientX;
    startW = sidebar.getBoundingClientRect().width;

    sidebarResizer.classList.add("resizing");
    document.body.classList.add("sidebar-resizing");

    window.addEventListener("mousemove", onDragMove, { passive: false });
    window.addEventListener("mouseup", onDragEnd);
    window.addEventListener("touchmove", onDragMove, { passive: false });
    window.addEventListener("touchend", onDragEnd);
    if (e.cancelable) e.preventDefault();
  }

  function onDragMove(e) {
    if (!isDragging) return;
    const currentX = e.type.startsWith("touch") ? e.touches[0].clientX : e.clientX;
    const delta = currentX - startX;
    const newWidth = Math.max(MIN_WIDTH, Math.min(startW + delta, Math.min(580, Math.floor(window.innerWidth * 0.55))));
    applySidebarWidth(newWidth, true);
    if (e.cancelable) e.preventDefault();
  }

  function onDragEnd() {
    if (!isDragging) return;
    isDragging = false;
    sidebarResizer.classList.remove("resizing");
    document.body.classList.remove("sidebar-resizing");

    window.removeEventListener("mousemove", onDragMove);
    window.removeEventListener("mouseup", onDragEnd);
    window.removeEventListener("touchmove", onDragMove);
    window.removeEventListener("touchend", onDragEnd);

    const finalWidth = sidebar.getBoundingClientRect().width;
    try {
      localStorage.setItem("floatchat_sidebar_w", Math.round(finalWidth));
    } catch (_) {}

    setTimeout(() => {
      if (typeof oceanLeafletMap !== "undefined" && oceanLeafletMap) {
        oceanLeafletMap.invalidateSize();
      }
    }, 50);
  }

  sidebarResizer.addEventListener("mousedown", onDragStart);
  sidebarResizer.addEventListener("touchstart", onDragStart, { passive: false });

  sidebarResizer.addEventListener("dblclick", () => {
    applySidebarWidth(DEFAULT_WIDTH, true);
    try {
      localStorage.removeItem("floatchat_sidebar_w");
    } catch (_) {}
  });
}
initSidebarResizer();

function startNewChat() {
  stopSpeaking();
  loadSeq++;                       // cancel any chat that is still loading
  listSeq++;
  conversationId = crypto.randomUUID();
  localStorage.setItem("floatchat-conv-id", conversationId);
  messagesEl.innerHTML = "";
  questionInput.value = "";
  welcomeCard.style.display = "";
  welcomeCard.style.opacity = "1";
  clearStatus();
  sidebar.classList.remove("open");
  switchTab("chat");
  loadConversations(searchInput?.value.trim() || "");
}
newChatBtn?.addEventListener("click", startNewChat);

// Quick question pills
document.querySelectorAll(".example-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.dataset.q;
    if (!q || isBusy) return;
    switchTab("chat");
    questionInput.value = q;
    askForm.dispatchEvent(new Event("submit"));
    sidebar.classList.remove("open");
  });
});

// ── Voice / Audio Response (Text-to-Speech) ──────────────────────────────────
let autoSpeakEnabled = localStorage.getItem("floatchat-auto-speak") === "true";
let activeSpeakingBtn = null;
let currentUtterance = null;
let wasAskedViaMic = false;

function prepareTextForSpeech(text) {
  if (!text) return "";
  let clean = text;
  // Drop markdown links [text](url) -> text
  clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  // Drop citation tags like [S1], [S2]
  clean = clean.replace(/\[S\d+\]/g, "");
  // Drop markdown symbols
  clean = clean.replace(/[*_#`~]/g, "");
  // Expand oceanographic terms and symbols for natural pronunciation
  clean = clean.replace(/°C\b/g, " degrees Celsius");
  clean = clean.replace(/\bpsu\b/gi, " practical salinity units");
  clean = clean.replace(/\bdbar\b/gi, " decibars");
  clean = clean.replace(/\bapprox\./gi, "approximately");
  clean = clean.replace(/\bvs\.\b/gi, "versus");
  clean = clean.replace(/(\d+)-(\d+)/g, "$1 to $2");
  clean = clean.replace(/\s+/g, " ").trim();
  return clean;
}

function getBestVoice() {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  return (
    voices.find(v => v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Google") || v.name.includes("Online"))) ||
    voices.find(v => v.lang === "en-US") ||
    voices.find(v => v.lang.startsWith("en")) ||
    voices[0] ||
    null
  );
}

if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => { getBestVoice(); };
}

function stopSpeaking() {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  if (activeSpeakingBtn) {
    activeSpeakingBtn.classList.remove("speaking");
    activeSpeakingBtn.innerHTML = "&#x1f50a; Listen";
    activeSpeakingBtn = null;
  }
  currentUtterance = null;
}

function toggleSpeakAnswer(text, btn) {
  if (!("speechSynthesis" in window)) return;
  if (activeSpeakingBtn === btn && window.speechSynthesis.speaking) {
    stopSpeaking();
    return;
  }
  stopSpeaking();

  const spokenText = prepareTextForSpeech(text);
  if (!spokenText) return;

  const utterance = new SpeechSynthesisUtterance(spokenText);
  const voice = getBestVoice();
  if (voice) utterance.voice = voice;
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  activeSpeakingBtn = btn;
  if (btn) {
    btn.classList.add("speaking");
    btn.innerHTML = "&#x23f9; Stop";
  }

  utterance.onend = () => {
    if (activeSpeakingBtn === btn) {
      btn.classList.remove("speaking");
      btn.innerHTML = "&#x1f50a; Listen";
      activeSpeakingBtn = null;
    }
    currentUtterance = null;
  };

  utterance.onerror = () => {
    if (activeSpeakingBtn === btn) {
      btn.classList.remove("speaking");
      btn.innerHTML = "&#x1f50a; Listen";
      activeSpeakingBtn = null;
    }
    currentUtterance = null;
  };

  currentUtterance = utterance;
  window.speechSynthesis.speak(utterance);
}

// ── Chat Messaging ────────────────────────────────────────────────────────────
function renderUser(text) {
  welcomeCard.style.display = "none";
  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `<div class="avatar">&#x1f464;</div><div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function renderTyping() {
  const row = document.createElement("div");
  row.className = "message-row bot";
  row.id = "typing-row";
  row.innerHTML = `
    <div class="avatar">&#x1f30a;</div>
    <div class="bubble">
      <div class="typing-indicator">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
    </div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function renderBotText(text) {
  welcomeCard.style.display = "none";
  const row = document.createElement("div");
  row.className = "message-row bot";
  const speakBtnHtml = ('speechSynthesis' in window)
    ? '<button class="action-btn speak-btn" title="Listen to audio response">&#x1f50a; Listen</button>'
    : "";
  row.innerHTML = `
    <div class="avatar">&#x1f30a;</div>
    <div class="bubble">
      <div class="answer-text">${escapeHtml(text)}</div>
      <div class="bubble-actions">
        <button class="action-btn copy-btn" title="Copy answer">&#x1f4cb; Copy</button>
        ${speakBtnHtml}
      </div>
    </div>
  `;
  messagesEl.appendChild(row);
  row.querySelector(".copy-btn")?.addEventListener("click", () => {
    navigator.clipboard.writeText(text).then(() => flashBtn(row.querySelector(".copy-btn"), "Copied!")).catch(() => {});
  });
  const speakBtn = row.querySelector(".speak-btn");
  if (speakBtn) {
    speakBtn.addEventListener("click", () => toggleSpeakAnswer(text, speakBtn));
  }
  scrollToBottom();
  return row;
}

// ── Technology badge rendering ──────────────────────────────────────────────
const TECH_BADGE_MAP = {
  "GenAI/LLM":          { icon: "🤖", label: "LLM",  cssClass: "tech-llm" },
  "NLP":                 { icon: "🔍", label: "NLP",  cssClass: "tech-nlp" },
  "RAG":                 { icon: "📚", label: "RAG",  cssClass: "tech-rag" },
  "Data Visualization":  { icon: "📊", label: "Viz",  cssClass: "tech-viz" },
};

/**
 * Build HTML for the technology badges strip.
 * Returns an empty string when the list is falsy or empty so the
 * caller can hide the container gracefully.
 */
function renderTechBadges(techList) {
  if (!techList || !Array.isArray(techList) || techList.length === 0) return "";
  const badges = techList.map(t => {
    const info = TECH_BADGE_MAP[t];
    if (!info) return `<span class="tech-badge" title="${escapeHtml(t)}">${escapeHtml(t)}</span>`;
    return `<span class="tech-badge ${info.cssClass}" title="${escapeHtml(t)}">${info.icon} ${info.label}</span>`;
  }).join("");
  return `<div class="tech-badges">${badges}</div>`;
}

// ── Answer helpers: knowledge detection, parser badge, sources panel ─────────
function isKnowledgeAnswer(data) {
  return data.task === "concept" || data.question_kind === "knowledge";
}

// Reflects what the backend actually reports in `parser_used`
// ("llm" | "rules"). If the field is missing we show nothing rather than guess.
function parserBadgeHtml(parserUsed) {
  if (parserUsed === "llm") {
    return `<span class="answer-badge parser-ai" title="The question was interpreted by the AI model">🧠 Understood by AI</span>`;
  }
  if (parserUsed === "rules") {
    return `<span class="answer-badge parser-rules" title="The question was interpreted by the built-in rule parser">📐 Understood by rules</span>`;
  }
  return "";
}

// The backend appends "\n\nSources: a, b" to knowledge answers; the sources now
// live in their own collapsible panel, so drop that footer to avoid duplication.
function stripSourcesFooter(answer, sources) {
  const text = answer || "";
  if (!sources || !sources.length) return text;
  return text.replace(/\n*\s*Sources:[^\n]*$/i, "").trimEnd();
}

function sourcesPanelHtml(sources) {
  if (!sources || !sources.length) return "";
  const items = sources.map(s => `<li class="source-item">📖 ${escapeHtml(s)}</li>`).join("");
  return `
    <details class="sources-panel">
      <summary class="sources-toggle">
        <span class="sources-toggle-label">Sources <span class="sources-count">${sources.length}</span></span>
        <span class="sources-chevron" aria-hidden="true">▾</span>
      </summary>
      <ul class="sources-list">${items}</ul>
    </details>
  `;
}

function renderBot(data, originalQuestion) {
  welcomeCard.style.display = "none";
  const { answer, variable, units, observation_count, stat, chart_data, date_range, ambiguous, answer_mode, task, discovery_data, sources, parser_used, question_kind, technologies_used } = data;
  const isKnowledge = isKnowledgeAnswer(data);

  const row = document.createElement("div");
  row.className = "message-row bot";

  // Badge: Basic vs Gemini
  const answerBadge = answer_mode === "gemini"
    ? `<span class="answer-badge gemini">✨ Gemini AI</span>`
    : `<span class="answer-badge basic">⚡ Basic Answer</span>`;
  const badgeHtml = answerBadge + parserBadgeHtml(parser_used);

  let statsHtml = "";
  if (!ambiguous && !isKnowledge && observation_count > 0 && task === "stat") {
    const chips = [];
    chips.push(`<div class="stat-chip"><span class="label">Observations</span><span class="value">${observation_count.toLocaleString()}</span></div>`);
    if (variable) chips.push(`<div class="stat-chip"><span class="label">Variable</span><span class="value">${variable} (${units || ""})</span></div>`);
    if (stat) chips.push(`<div class="stat-chip"><span class="label">${stat.stat.toUpperCase()}</span><span class="value">${stat.value}</span></div>`);
    if (date_range) chips.push(`<div class="stat-chip"><span class="label">Period</span><span class="value">${date_range}</span></div>`);
    if (chips.length) statsHtml = `<div class="stats-strip">${chips.join("")}</div>`;
  }

  // Render compact discovery table if discovery data present
  let discoveryTableHtml = "";
  if (discovery_data && discovery_data.floats && discovery_data.floats.length > 0) {
    const previewFloats = discovery_data.floats.slice(0, 5);
    const rows = previewFloats.map(f => `
      <tr>
        <td><strong>${escapeHtml(f.platform)}</strong></td>
        <td>${f.profile_count}</td>
        <td>${(f.first_date||'').substring(0,10)} – ${(f.last_date||'').substring(0,10)}</td>
        <td>${f.avg_max_depth ? f.avg_max_depth.toFixed(1) + ' dbar' : '—'}</td>
      </tr>
    `).join("");
    discoveryTableHtml = `
      <div class="chat-table-wrap" style="margin: 10px 0; overflow-x: auto;">
        <table class="floats-table compact">
          <thead><tr><th>Float</th><th>Profiles</th><th>Dates</th><th>Max Depth</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  const sourcesHtml = sourcesPanelHtml(sources);
  const answerText = stripSourcesFooter(answer, sources);

  const speakBtnHtml = ('speechSynthesis' in window)
    ? '<button class="action-btn speak-btn" title="Listen to audio response">&#x1f50a; Listen</button>'
    : "";
  const exportBtnHtml = (!isKnowledge && observation_count > 0) ? '<button class="action-btn export-csv-btn" title="Export CSV">&#x1f4be; Export CSV</button>' : "";
  const imageBtnHtml = chart_data ? '<button class="action-btn download-img-btn" title="Download chart as PNG image">&#x1f5bc;&#xfe0f; Download image</button>' : "";

  // Extract or detect float platform for dive simulator shortcut
  let simFloatId = null;
  if (data.platform) {
    simFloatId = String(data.platform);
  } else if (discovery_data && Array.isArray(discovery_data.floats) && discovery_data.floats.length > 0) {
    simFloatId = String(discovery_data.floats[0].platform);
  } else {
    const floatMatch = (originalQuestion || "").match(/\b(19\d{5}|29\d{5})\b/) || (answer || "").match(/\b(19\d{5}|29\d{5})\b/);
    if (floatMatch) simFloatId = floatMatch[1];
  }
  const simBtnHtml = simFloatId
    ? `<button class="action-btn sim-float-btn" data-float="${escapeHtml(simFloatId)}" title="Launch 4D Mission Simulator for Float ${escapeHtml(simFloatId)}">🤿 Dive Sim: ${escapeHtml(simFloatId)}</button>`
    : `<button class="action-btn sim-float-btn" title="Open ARGO 4D Mission Simulator">🤿 Dive Sim</button>`;

  const techBadgesHtml = renderTechBadges(technologies_used);

  const actionBtns = `
    <div class="bubble-actions">
      <button class="action-btn copy-btn" title="Copy answer">&#x1f4cb; Copy</button>
      ${speakBtnHtml}
      ${simBtnHtml}
      ${imageBtnHtml}
      ${exportBtnHtml}
    </div>
  `;

  row.innerHTML = `
    <div class="avatar">&#x1f30a;</div>
    <div class="bubble">
      <div class="bubble-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        ${badgeHtml}
      </div>
      <div class="answer-text">${escapeHtml(answerText)}</div>
      ${statsHtml}
      ${discoveryTableHtml}
      ${sourcesHtml}
      ${chart_data ? '<div class="chart-wrap" id="chart-' + Date.now() + '"></div>' : ""}
      ${actionBtns}
      ${techBadgesHtml}
    </div>
  `;

  messagesEl.appendChild(row);

  if (chart_data) {
    const chartEl = row.querySelector("[id^='chart-']");
    try {
      const chartObj = typeof chart_data === "string" ? JSON.parse(chart_data) : chart_data;
      if (!chartObj || !Array.isArray(chartObj.data) || chartObj.data.length === 0) {
        showChartState(chartEl, "No chart data is available for this question.");
      } else {
        // Preserve backend chart types (including depth-interval/profile charts), while applying dark styling.
        renderPlotlyChart(chartEl, chartObj.data, chartObj.layout || {}, chartObj.config || {});
      }
    } catch (err) {
      showChartState(chartEl, `Chart data could not be read: ${err.message || "invalid chart data"}`, true);
    }
  }

  row.querySelector(".copy-btn")?.addEventListener("click", () => {
    navigator.clipboard.writeText(answer).then(() => flashBtn(row.querySelector(".copy-btn"), "Copied!")).catch(() => {});
  });
  row.querySelector(".export-csv-btn")?.addEventListener("click", () => triggerCsvExport());
  row.querySelector(".download-img-btn")?.addEventListener("click", () => downloadChartImage(row.querySelector("[id^='chart-']"), row.querySelector(".download-img-btn")));
  const speakBtn = row.querySelector(".speak-btn");
  if (speakBtn) {
    speakBtn.addEventListener("click", () => toggleSpeakAnswer(answerText, speakBtn));
  }
  const simBtn = row.querySelector(".sim-float-btn");
  if (simBtn) {
    simBtn.addEventListener("click", () => {
      const p = simBtn.dataset.float;
      if (p) openSimulatorForFloat(p);
      else switchTab("simulator");
    });
  }
  scrollToBottom();
  return row;
}

function renderError(message) {
  welcomeCard.style.display = "none";
  const row = document.createElement("div");
  row.className = "message-row bot";
  row.innerHTML = `
    <div class="avatar">&#x26a0;&#xfe0f;</div>
    <div class="bubble error">
      <strong>Notice</strong><br/>${escapeHtml(message)}
    </div>
  `;
  messagesEl.appendChild(row);
  scrollToBottom();
}

async function sendMessage(question) {
  if (!question || isBusy) return;
  setBusy(true);
  clearStatus();
  lastMessageData = { question };

  const sentConvId = conversationId;
  renderUser(question);
  const typingEl = renderTyping();

  try {
    const resp = await fetch(ENDPOINTS.chat, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ message: question, conversation_id: sentConvId }),
    });

    typingEl.remove();
    if (resp.status === 401) { showAuth(); return; }
    const data = await resp.json();

    // The user started a new chat or opened another one while this was running:
    // the answer is saved on the server, but must not appear in the wrong view.
    if (conversationId !== sentConvId) {
      await loadConversations(searchInput?.value.trim() || "");
      return;
    }

    if (!resp.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map(item => item?.msg || item?.message || String(item)).join("; ")
        : (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || `Server returned error (${resp.status})`));
      renderError(detail);
      return;
    }

    const askedWithMic = wasAskedViaMic;
    wasAskedViaMic = false;

    const botRow = renderBot(data, question);
    if (autoSpeakEnabled || askedWithMic) {
      const speakBtn = botRow?.querySelector(".speak-btn");
      const cleanAnswer = stripSourcesFooter(data.answer, data.sources);
      toggleSpeakAnswer(cleanAnswer, speakBtn);
    }
    await loadConversations(searchInput?.value || "");
  } catch (err) {
    typingEl.remove();
    renderError("Could not connect to FloatChat backend. Please verify the server is running.");
  } finally {
    setBusy(false);
  }
}

askForm?.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = questionInput.value.trim();
  if (!q) return;
  questionInput.value = "";
  questionInput.style.height = "auto";
  sendMessage(q);
});

// ── Export CSV ────────────────────────────────────────────────────────────────
async function triggerCsvExport() {
  try {
    const resp = await fetch(ENDPOINTS.export, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    if (resp.status === 401 || resp.status === 403) { showAuth(); return; }
    if (!resp.ok) {
      let detail = "Export failed.";
      try { const d = await resp.json(); if (typeof d.detail === "string") detail = d.detail; } catch (_) {}
      showStatus(detail, true);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `floatchat_export_${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showStatus("CSV exported successfully.");
    setTimeout(clearStatus, 3000);
  } catch (_) {
    showStatus("Export failed.", true);
  }
}
exportBtn?.addEventListener("click", triggerCsvExport);

// ── Export Scientific PDF Report ─────────────────────────────────────────────
async function triggerPdfExport() {
  try {
    showStatus("Generating Scientific Oceanographic PDF Report...");
    const resp = await fetch(`${API_BASE}/api/export/pdf`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    if (resp.status === 401 || resp.status === 403) { showAuth(); return; }
    if (!resp.ok) {
      let detail = "PDF Export failed.";
      try { const d = await resp.json(); if (typeof d.detail === "string") detail = d.detail; } catch (_) {}
      showStatus(detail, true);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `floatchat_scientific_report_${Date.now()}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showStatus("Scientific PDF Report downloaded successfully.");
    setTimeout(clearStatus, 3000);
  } catch (_) {
    showStatus("Network error downloading PDF report.", true);
  }
}
const exportPdfBtn = document.getElementById("export-pdf-btn");
exportPdfBtn?.addEventListener("click", triggerPdfExport);

// Download a rendered chart as a PNG (2x resolution). Works for restored/history charts too.
async function downloadChartImage(chartEl, btn) {
  if (!chartEl || !window.Plotly || !chartEl.data || typeof Plotly.downloadImage !== "function") {
    showStatus("This chart is not ready to download yet (or has no data).", true);
    setTimeout(clearStatus, 3500);
    return;
  }
  try {
    const w = Math.max(chartEl.clientWidth || 0, 800);
    const h = Math.max(chartEl.clientHeight || 0, 450);
    await Plotly.downloadImage(chartEl, { format: "png", filename: `floatchat_chart_${Date.now()}`, width: w, height: h, scale: 2 });
    flashBtn(btn, "Saved!");
  } catch (err) {
    console.error("Chart image download failed:", err);
    showStatus("Could not create the chart image.", true);
    setTimeout(clearStatus, 3500);
  }
}

function downloadBlob(content, filename, contentType) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Share chat (read-only snapshot link) ──────────────────────────────────────
const shareBtn        = document.getElementById("share-btn");
const shareModal      = document.getElementById("share-modal");
const shareLinkInput  = document.getElementById("share-link-input");
const shareStatusEl   = document.getElementById("share-status");
const shareCopyBtn    = document.getElementById("share-copy-btn");
const shareNativeBtn  = document.getElementById("share-native-btn");
const shareRefreshBtn = document.getElementById("share-refresh-btn");
const shareStopBtn    = document.getElementById("share-stop-btn");

function shareUrlFor(token) { return `${window.location.origin}/?share=${encodeURIComponent(token)}`; }
function setShareStatus(msg, isError = false) {
  if (!shareStatusEl) return;
  shareStatusEl.textContent = msg || "";
  shareStatusEl.classList.toggle("is-error", !!isError);
}
function closeShareModal() { if (shareModal) shareModal.hidden = true; }

async function createOrRefreshShare() {
  const resp = await fetch(`${ENDPOINTS.conversations}/${encodeURIComponent(conversationId)}/share`, { method: "POST", headers: authHeaders() });
  if (resp.status === 401 || resp.status === 403) { closeShareModal(); showAuth(); return null; }
  let data = {};
  try { data = await resp.json(); } catch (_) {}
  if (!resp.ok) {
    setShareStatus(resp.status === 404 ? "This chat is not saved yet. Ask a question first, then share it." : apiErrorText(data, "Could not create the share link."), true);
    return null;
  }
  return data;
}

shareBtn?.addEventListener("click", async () => {
  if (!authToken) { showStatus("Sign in to share chats.", true); return; }
  shareModal.hidden = false;
  shareLinkInput.value = "";
  shareNativeBtn.hidden = !navigator.share;
  setShareStatus("Creating link…");
  const data = await createOrRefreshShare();
  if (!data) { shareLinkInput.value = ""; return; }
  shareLinkInput.value = shareUrlFor(data.token);
  setShareStatus("Link ready. It shows this chat as of now.");
  shareLinkInput.focus(); shareLinkInput.select();
});

shareCopyBtn?.addEventListener("click", async () => {
  if (!shareLinkInput.value) return;
  try { await navigator.clipboard.writeText(shareLinkInput.value); setShareStatus("Link copied to clipboard."); }
  catch (_) { shareLinkInput.select(); setShareStatus("Press Ctrl+C (or ⌘C) to copy the selected link."); }
});

shareNativeBtn?.addEventListener("click", async () => {
  if (!shareLinkInput.value || !navigator.share) return;
  try { await navigator.share({ title: "FloatChat conversation", text: "A FloatChat ARGO ocean-data chat", url: shareLinkInput.value }); }
  catch (_) { /* user dismissed the share sheet */ }
});

shareRefreshBtn?.addEventListener("click", async () => {
  setShareStatus("Updating…");
  const data = await createOrRefreshShare();
  if (data) { shareLinkInput.value = shareUrlFor(data.token); setShareStatus("Link updated with the latest messages."); }
});

shareStopBtn?.addEventListener("click", async () => {
  if (!window.confirm("Stop sharing? The link will stop working for everyone.")) return;
  try {
    const resp = await fetch(`${ENDPOINTS.conversations}/${encodeURIComponent(conversationId)}/share`, { method: "DELETE", headers: authHeaders() });
    if (resp.status === 401 || resp.status === 403) { closeShareModal(); showAuth(); return; }
    if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);
    shareLinkInput.value = "";
    setShareStatus("Sharing stopped. The old link no longer works.");
  } catch (_) { setShareStatus("Could not stop sharing. Please try again.", true); }
});

document.getElementById("share-modal-close")?.addEventListener("click", closeShareModal);
shareModal?.addEventListener("click", (e) => { if (e.target === shareModal) closeShareModal(); });

// Read-only view for a shared link (?share=TOKEN): no sign-in, no input box, no sidebar.
async function showSharedChat(token) {
  document.body.classList.add("shared-view");
  authScreen.hidden = true;
  appShell.hidden = false;
  document.getElementById("shared-banner").hidden = false;
  welcomeCard.style.display = "none";
  const bannerText = document.getElementById("shared-banner-text");
  try {
    const resp = await fetch(`${ENDPOINTS.shared}/${encodeURIComponent(token)}`, { cache: "no-store" });
    if (!resp.ok) {
      bannerText.textContent = "Shared chat";
      renderBotText(resp.status === 404 ? "This shared chat does not exist or is no longer shared." : `Could not open this shared chat (${resp.status}).`);
      return;
    }
    const chat = await resp.json();
    bannerText.textContent = `Shared chat (read-only): ${chat.title || ""}`;
    document.title = `${chat.title || "Shared chat"} · FloatChat`;
    (chat.messages || []).forEach(msg => {
      try {
        if (msg.role === "user") renderUser(msg.content);
        else if (msg.role === "assistant" && msg.response_data && typeof msg.response_data === "object") renderBot(msg.response_data, "");
        else if (msg.role === "assistant") renderBotText(msg.content);
      } catch (err) { renderBotText(msg.content || ""); }
    });
    scrollToBottom();
  } catch (_) {
    renderBotText("Could not connect to the server to load this shared chat.");
  }
}

// ── Voice Search (Speech Recognition with Marine Acoustic Normalizer) ─────────
function normalizeMarineSpeechTranscript(raw) {
  if (!raw) return "";
  let t = raw;

  const replacements = [
    [/\bthermo\s*cline[s]?\b/gi, "thermocline"],
    [/\bhalo\s*cline[s]?\b/gi, "halocline"],
    [/\bpycno\s*cline[s]?\b/gi, "pycnocline"],
    [/\bmixed\s*layer\s*depth\b/gi, "mixed layer depth"],
    [/\bm\s*l\s*d\b/gi, "MLD"],
    [/\bs\s*o\s*f\s*a\s*r\b/gi, "SOFAR"],
    [/\bso\s*far\s*axis\b/gi, "SOFAR axis"],
    [/\bargo\s*float[s]?\b/gi, "ARGO float"],
    [/\bcargo\s*float[s]?\b/gi, "ARGO float"],
    [/\bp\s*s\s*u\b/gi, "PSU"],
    [/\bd\s*bars?\b/gi, "dbar"],
    [/\bdeep\s*bars?\b/gi, "dbar"],
    [/\bdeci\s*bars?\b/gi, "dbar"],
    [/\bbay\s*of\s*bangle\b/gi, "Bay of Bengal"],
    [/\bbay\s*of\s*bengal\b/gi, "Bay of Bengal"],
    [/\barabian\s*sea\b/gi, "Arabian Sea"],
    [/\bisopycnal[s]?\b/gi, "isopycnal"],
    [/\bsigma\s*theta\b/gi, "sigma-theta"],
  ];

  for (const [pattern, repl] of replacements) {
    t = t.replace(pattern, repl);
  }

  const digitWords = {
    zero: "0", one: "1", two: "2", three: "3", four: "4",
    five: "5", six: "6", seven: "7", eight: "8", nine: "9"
  };
  t = t.replace(/\b(?:zero|one|two|three|four|five|six|seven|eight|nine)(?:\s+(?:zero|one|two|three|four|five|six|seven|eight|nine)){6}\b/gi, (match) => {
    return match.toLowerCase().split(/\s+/).map(w => digitWords[w] || w).join("");
  });

  return t.trim();
}

const micBtn = document.getElementById("mic-btn");
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognizer = new SpeechRec();
  recognizer.continuous = false;
  recognizer.interimResults = true;
  recognizer.lang = "en-US";

  recognizer.onstart = () => {
    micBtn.classList.add("recording");
    if (voiceVisualizer) voiceVisualizer.hidden = false;
    if (voiceStatusText) voiceStatusText.textContent = "Listening... Speak your ocean question";
    showStatus("🎙️ Listening... Speak your ocean question (e.g. 'What is the average temperature in January 2023?')");
  };

  recognizer.onresult = (e) => {
    let interim = "";
    let finalTranscript = "";
    for (let i = e.resultIndex; i < e.results.length; ++i) {
      if (e.results[i].isFinal) {
        finalTranscript += e.results[i][0].transcript;
      } else {
        interim += e.results[i][0].transcript;
      }
    }
    const currentText = finalTranscript || interim;
    const normalized = normalizeMarineSpeechTranscript(currentText);
    if (questionInput) questionInput.value = normalized;
    if (voiceStatusText) voiceStatusText.textContent = `Heard: "${normalized}"`;

    if (finalTranscript) {
      wasAskedViaMic = true;
      if (voiceVisualizer) voiceVisualizer.hidden = true;
      askForm?.dispatchEvent(new Event("submit"));
    }
  };

  recognizer.onerror = (e) => {
    console.warn("Speech recognition error:", e);
    if (voiceVisualizer) voiceVisualizer.hidden = true;
    showStatus(e.error === "not-allowed" ? "Microphone access denied. Please allow microphone permission in your browser." : "Voice recognition failed. Please try again.", true);
  };

  recognizer.onend = () => {
    micBtn.classList.remove("recording");
    if (voiceVisualizer) voiceVisualizer.hidden = true;
    clearStatus();
  };

  voiceCancelBtn?.addEventListener("click", () => {
    try { recognizer.abort(); } catch (_) {}
    micBtn.classList.remove("recording");
    if (voiceVisualizer) voiceVisualizer.hidden = true;
    clearStatus();
  });

  micBtn?.addEventListener("click", () => {
    if (micBtn.classList.contains("recording")) {
      recognizer.stop();
    } else {
      recognizer.start();
    }
  });
} else if (micBtn) {
  micBtn.addEventListener("click", () => {
    showStatus("Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari.", true);
    setTimeout(clearStatus, 4000);
  });
}

// ── Audio Response Toggle (Topbar) ───────────────────────────────────────────
const speechToggleBtn = document.getElementById("speech-toggle-btn");
const speechIconOn    = document.getElementById("speech-icon-on");
const speechIconOff   = document.getElementById("speech-icon-off");

function applySpeechToggle(enabled) {
  autoSpeakEnabled = !!enabled;
  localStorage.setItem("floatchat-auto-speak", autoSpeakEnabled ? "true" : "false");
  if (speechIconOn && speechIconOff) {
    speechIconOn.style.display = autoSpeakEnabled ? "" : "none";
    speechIconOff.style.display = autoSpeakEnabled ? "none" : "";
  }
  speechToggleBtn?.classList.toggle("active", autoSpeakEnabled);
  if (!autoSpeakEnabled) {
    stopSpeaking();
  }
}

speechToggleBtn?.addEventListener("click", () => {
  applySpeechToggle(!autoSpeakEnabled);
  showStatus(autoSpeakEnabled ? "Voice response enabled (answers will be read aloud)" : "Voice response muted", false);
  setTimeout(clearStatus, 2500);
});
applySpeechToggle(autoSpeakEnabled);

// ── Dark / Light Theme Toggle ─────────────────────────────────────────────────
const themeToggleBtn = document.getElementById("theme-toggle-btn");
const themeIconMoon = document.getElementById("theme-icon-moon");
const themeIconSun = document.getElementById("theme-icon-sun");

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("floatchat-theme", theme);
  if (themeIconMoon && themeIconSun) {
    if (theme === "light") {
      themeIconMoon.style.display = "none";
      themeIconSun.style.display = "";
    } else {
      themeIconMoon.style.display = "";
      themeIconSun.style.display = "none";
    }
  }
  // Dynamically update background and font on all rendered Plotly charts
  const isLight = theme === "light";
  const paperBg = isLight ? "#ffffff" : "#1e293b";
  const plotBg  = isLight ? "#f8fafc" : "#0f172a";
  const fontCol = isLight ? "#334155" : "#94a3b8";
  document.querySelectorAll(".chart-plotly").forEach(chartEl => {
    if (chartEl && chartEl.data && window.Plotly) {
      try {
        Plotly.relayout(chartEl, {
          paper_bgcolor: paperBg,
          plot_bgcolor: plotBg,
          "font.color": fontCol
        });
      } catch (_) {}
    }
  });
}

themeToggleBtn?.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current === "dark" ? "light" : "dark");
});
applyTheme(localStorage.getItem("floatchat-theme") || "dark");

// ── Health Modal ──────────────────────────────────────────────────────────────
async function healthPing() {
  try {
    const resp = await fetch(ENDPOINTS.health);
    const data = await resp.json();
    return data;
  } catch (_) { return null; }
}

healthBtn?.addEventListener("click", async () => {
  healthModal.hidden = false;
  healthContent.textContent = "Checking server...";
  const data = await healthPing();
  if (!data) {
    healthContent.innerHTML = `<span style="color:#f43f5e">● Server unreachable</span>`;
    return;
  }
  const db = data.db || {};
  const ragMode = data.rag_mode || "tfidf";
  const techStatus = data.technologies || {};
  healthContent.innerHTML = `
    <p><strong>Status:</strong> <span style="color:#34d399">● ${data.status}</span></p>
    <p><strong>Answer Mode:</strong> ${data.answer_mode === "gemini" ? "Gemini AI" : "Rules Engine (Zero AI Quota)"}</p>
    <p><strong>Gemini Ready:</strong> ${data.gemini_ready ? "Yes" : "No (Offline rules mode)"}</p>
    <p><strong>RAG Mode:</strong> ${ragMode === "embedding" ? "Embedding-based (Gemini)" : "TF-IDF (Offline)"}</p>
    <p><strong>Database:</strong> ${db.profiles || 0} profiles, ${db.measurements || 0} measurements</p>
    <hr style="border-color: rgba(255,255,255,0.1); margin: 10px 0;">
    <p><strong>Active Technologies:</strong></p>
    <div class="tech-badges" style="margin-top: 6px;">
      <span class="tech-badge tech-nlp" title="NLP">🔍 NLP</span>
      ${data.gemini_ready ? '<span class="tech-badge tech-llm" title="GenAI/LLM">🤖 LLM</span>' : ''}
      <span class="tech-badge tech-rag" title="RAG">📚 RAG</span>
      <span class="tech-badge tech-viz" title="Data Visualization">📊 Viz</span>
    </div>
  `;
});
healthClose?.addEventListener("click", () => healthModal.hidden = true);
healthModal?.addEventListener("click", (e) => { if (e.target === healthModal) healthModal.hidden = true; });

// ── ARGO 4D Mission Simulator & Deep Sound (SOFAR) Sonar Engine ─────────────
let simCurrentFloat = null;
let simProfileData = null;
let simDepth = 0.0;            // 0.0 to 2000.0 dbar
let simIsPlaying = false;
let simSpeed = 1;              // 1x, 2x, 5x
let simMissionPhase = 1;       // 1: Surface, 2: Descent, 3: Drift, 4: Abyss, 5: Ascent
let simDriftFrames = 0;
let simCanvasCtx = null;
let simAnimId = null;
let simParticles = [];
let simBubbles = [];
let simSonarRings = [];
let simRadioRings = [];
let simChartRendered = false;

// Initialize floating marine snow / plankton particles
function initSimParticles() {
  simParticles = [];
  for (let i = 0; i < 45; i++) {
    simParticles.push({
      x: Math.random() * 420,
      y: Math.random() * 580,
      radius: Math.random() * 1.5 + 0.5,
      speedY: Math.random() * 0.3 + 0.1,
      swaySpeed: Math.random() * 0.02 + 0.01,
      swayAmp: Math.random() * 15 + 5,
      baseX: Math.random() * 420,
      alpha: Math.random() * 0.6 + 0.2
    });
  }
}

async function ensureSimulatorFloatsLoaded() {
  if (simFloatSelect && simFloatSelect.options.length > 0) return;
  try {
    const resp = await fetch(ENDPOINTS.floats, { headers: authHeaders() });
    if (!resp.ok) return;
    const data = await resp.json();
    const floats = Array.isArray(data.floats) ? data.floats : [];
    if (!floats.length) return;
    simFloatSelect.innerHTML = floats.map(f =>
      `<option value="${escapeHtml(f.platform)}">Float ${escapeHtml(f.platform)} (${f.profile_count} profiles)</option>`
    ).join("");
    if (!simCurrentFloat && floats[0]) {
      simCurrentFloat = floats[0].platform;
    }
  } catch (e) {
    console.error("Failed to load floats for simulator:", e);
  }
}

async function initSimulator() {
  await ensureSimulatorFloatsLoaded();
  if (!simCurrentFloat && simFloatSelect && simFloatSelect.value) {
    simCurrentFloat = simFloatSelect.value;
  }
  if (simCurrentFloat && (!simProfileData || simProfileData.platform !== simCurrentFloat)) {
    await loadDiveProfile(simCurrentFloat);
  }
  if (!simCanvasCtx && simOceanCanvas) {
    simCanvasCtx = simOceanCanvas.getContext("2d");
    initSimParticles();
    startSimAnimation();
  }
}

async function openSimulatorForFloat(platform) {
  if (!platform) return;
  switchTab("simulator");
  await ensureSimulatorFloatsLoaded();
  if (simFloatSelect) {
    simFloatSelect.value = platform;
  }
  await loadDiveProfile(platform);
}

async function loadDiveProfile(platform) {
  if (!platform) return;
  simCurrentFloat = platform;
  try {
    showStatus(`Loading dive profile and acoustic sound speed for float ${platform}…`);
    const resp = await fetch(ENDPOINTS.diveProfile(platform), { headers: authHeaders() });
    if (!resp.ok) {
      showStatus(`Could not load dive profile for float ${platform}`, true);
      return;
    }
    const data = await resp.json();
    simProfileData = data;
    currentSimData = data;
    clearStatus();

    // Update Ocean Physics metrics cards
    if (simPhysMld) {
      simPhysMld.textContent = data.mixed_layer_depth != null ? `${data.mixed_layer_depth} dbar` : "Not detected";
    }
    const simPhysBlt = document.getElementById("sim-phys-blt");
    if (simPhysBlt) {
      simPhysBlt.textContent = data.barrier_layer_thickness != null ? `${data.barrier_layer_thickness} dbar` : "0.0 dbar";
      simPhysBlt.title = "Barrier Layer Thickness = MLD(Temp) - MLD(Density). Barrier layers inhibit vertical heat exchange.";
    }
    if (simPhysThermocline) {
      simPhysThermocline.textContent = data.thermocline_depth != null ? `${data.thermocline_depth} dbar` : "Not detected";
    }
    if (simPhysSofar) {
      simPhysSofar.textContent = (data.sofar_depth != null && data.sofar_speed != null)
        ? `${data.sofar_depth} dbar (${data.sofar_speed} m/s)`
        : "Not detected";
    }

    // Hover text explains "Not detected" and the approximate SOFAR depth (method notes from the API).
    if (simPhysMld) simPhysMld.title = data.mixed_layer_note || "Temperature-based mixed layer depth (0.2 °C drop from the 10 dbar value)";
    if (simPhysThermocline) simPhysThermocline.title = "Depth of the strongest temperature gradient in the upper 500 dbar";
    if (simPhysSofar) simPhysSofar.title = data.sofar_note || "Sound-speed minimum (Mackenzie 1981)";

    if (simChartMode === "ts") {
      renderTsDiagram(data);
    } else {
      renderSimulatorCurves(data);
    }
    updateSimulatorHud(simDepth);
  } catch (err) {
    console.error("Failed to load dive profile:", err);
    showStatus("Could not connect to fetch dive profile", true);
  }
}

function renderSimulatorCurves(data) {
  if (!simPlotlyChart || !data || !Array.isArray(data.levels) || data.levels.length === 0) return;
  const levels = data.levels;
  const depths = levels.map(l => l.pressure);
  const temps  = levels.map(l => l.temperature);
  const sals   = levels.map(l => l.salinity);
  const speeds = levels.map(l => l.sound_speed);

  const traces = [
    {
      x: temps,
      y: depths,
      xaxis: "x1",
      yaxis: "y1",
      name: "Temp (°C)",
      type: "scatter",
      mode: "lines",
      line: { color: "#f43f5e", width: 2.5 },
      hovertemplate: "Depth: %{y:.1f} dbar<br>Temp: %{x:.2f} °C<extra></extra>"
    },
    {
      x: sals,
      y: depths,
      xaxis: "x2",
      yaxis: "y1",
      name: "Salinity (PSU)",
      type: "scatter",
      mode: "lines",
      line: { color: "#38bdf8", width: 2 },
      hovertemplate: "Depth: %{y:.1f} dbar<br>Salinity: %{x:.3f} PSU<extra></extra>"
    },
    {
      x: speeds,
      y: depths,
      xaxis: "x3",
      yaxis: "y1",
      name: "Sound Speed (m/s)",
      type: "scatter",
      mode: "lines",
      line: { color: "#a78bfa", width: 2.5 },
      hovertemplate: "Depth: %{y:.1f} dbar<br>Sound: %{x:.1f} m/s<extra></extra>"
    }
  ];

  const shapes = [];

  // SOFAR axis reference line
  if (data.sofar_depth != null) {
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y1",
      y0: data.sofar_depth,
      y1: data.sofar_depth,
      line: { color: "#c084fc", width: 1.5, dash: "dash" }
    });
  }

  // Mixed Layer Depth line
  if (data.mixed_layer_depth != null) {
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y1",
      y0: data.mixed_layer_depth,
      y1: data.mixed_layer_depth,
      line: { color: "#38bdf8", width: 1.5, dash: "dot" }
    });
  }

  // Active Float Depth indicator cursor (yellow)
  shapes.push({
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y1",
    y0: simDepth,
    y1: simDepth,
    line: { color: "#facc15", width: 2 }
  });

  const annotations = [];
  if (data.sofar_depth != null) {
    annotations.push({
      xref: "paper",
      x: 0.98,
      yref: "y1",
      y: data.sofar_depth,
      text: "SOFAR Channel Axis",
      showarrow: false,
      font: { color: "#c084fc", size: 10 },
      xanchor: "right",
      yanchor: "bottom"
    });
  }
  if (data.mixed_layer_depth != null) {
    annotations.push({
      xref: "paper",
      x: 0.02,
      yref: "y1",
      y: data.mixed_layer_depth,
      text: "MLD",
      showarrow: false,
      font: { color: "#38bdf8", size: 10 },
      xanchor: "left",
      yanchor: "bottom"
    });
  }

  const layout = {
    xaxis: {
      domain: [0, 0.30],
      title: { text: "Temp (°C)", font: { color: "#f43f5e", size: 11 } },
      tickfont: { color: "#f43f5e", size: 9 },
      gridcolor: "#334155"
    },
    xaxis2: {
      domain: [0.35, 0.65],
      anchor: "y1",
      title: { text: "Salinity (PSU)", font: { color: "#38bdf8", size: 11 } },
      tickfont: { color: "#38bdf8", size: 9 },
      gridcolor: "#334155"
    },
    xaxis3: {
      domain: [0.70, 1.0],
      anchor: "y1",
      title: { text: "Sound (m/s)", font: { color: "#a78bfa", size: 11 } },
      tickfont: { color: "#a78bfa", size: 9 },
      gridcolor: "#334155"
    },
    yaxis: {
      anchor: "x1",
      autorange: "reversed",
      range: [0, 2050],
      title: { text: "Depth / Pressure (dbar)", font: { size: 11 } },
      gridcolor: "#334155"
    },
    shapes,
    annotations,
    margin: { l: 55, r: 15, t: 25, b: 45 },
    showlegend: false
  };

  renderPlotlyChart(simPlotlyChart, traces, layout);
  simChartRendered = true;
}

let simChartMode = "vertical";
let currentSimData = null;

const btnChartVertical = document.getElementById("btn-chart-vertical");
const btnChartTs = document.getElementById("btn-chart-ts");
const simChartTitle = document.getElementById("sim-chart-title");

btnChartVertical?.addEventListener("click", () => {
  simChartMode = "vertical";
  btnChartVertical.classList.add("active");
  btnChartTs?.classList.remove("active");
  if (simChartTitle) simChartTitle.textContent = "Vertical In-Situ Curves (Temperature, Salinity & Sound Speed)";
  if (currentSimData) renderSimulatorCurves(currentSimData);
});

btnChartTs?.addEventListener("click", () => {
  simChartMode = "ts";
  btnChartTs.classList.add("active");
  btnChartVertical?.classList.remove("active");
  if (simChartTitle) simChartTitle.textContent = "T-S Diagram (Temperature vs. Salinity with Potential Density Isopycnals)";
  if (currentSimData) renderTsDiagram(currentSimData);
});

function renderTsDiagram(data) {
  if (!simPlotlyChart || !data || !Array.isArray(data.levels) || data.levels.length === 0) return;
  const levels = data.levels.filter(l => l.temperature != null && l.salinity != null);
  if (!levels.length) return;

  const salinities = levels.map(l => l.salinity);
  const temps = levels.map(l => l.temperature);
  const pressures = levels.map(l => l.pressure);
  const hoverTexts = levels.map(l =>
    `<b>Float #${data.platform || ''}</b><br>` +
    `Depth: ${l.pressure} dbar<br>` +
    `Temp: ${l.temperature} °C<br>` +
    `Salinity: ${l.salinity} PSU<br>` +
    `σθ: ${l.sigma_theta != null ? l.sigma_theta + ' kg/m³' : 'N/A'}<br>` +
    `Water Mass: <i>${l.water_mass || 'Unclassified'}</i>`
  );

  const traces = [];

  // Isopycnal background contour curves (UNESCO potential density sigma_theta)
  const isopycnals = [
    { sig: 21.0, pts: [] }, { sig: 22.0, pts: [] }, { sig: 23.0, pts: [] },
    { sig: 24.0, pts: [] }, { sig: 25.0, pts: [] }, { sig: 26.0, pts: [] },
    { sig: 27.0, pts: [] }, { sig: 27.5, pts: [] }
  ];

  isopycnals.forEach(({ sig, pts }) => {
    for (let s = 31.0; s <= 36.5; s += 0.5) {
      let tLow = -2.0, tHigh = 32.0, tMid = 15.0;
      for (let iter = 0; iter < 18; iter++) {
        tMid = (tLow + tHigh) / 2.0;
        const rhow = 999.84 + 0.0679 * tMid - 0.00909 * tMid * tMid + 0.000100 * tMid * tMid * tMid;
        const A = 0.824 - 0.00408 * tMid + 0.000076 * tMid * tMid;
        const B = -0.00572 + 0.000102 * tMid;
        const C = 0.000483;
        const estSig = rhow + A * s + B * Math.pow(s, 1.5) + C * s * s - 1000.0;
        if (estSig > sig) tLow = tMid;
        else tHigh = tMid;
      }
      if (tMid >= 0 && tMid <= 32) pts.push({ s, t: tMid });
    }
    if (pts.length >= 2) {
      traces.push({
        x: pts.map(p => p.s),
        y: pts.map(p => p.t),
        mode: "lines",
        line: { color: "rgba(148, 163, 184, 0.28)", width: 1, dash: "dot" },
        hoverinfo: "text",
        text: `σθ = ${sig} kg/m³`,
        showlegend: false
      });
    }
  });

  // Profile T-S trajectory path
  traces.push({
    x: salinities,
    y: temps,
    mode: "lines",
    line: { color: "rgba(56, 189, 248, 0.5)", width: 2 },
    hoverinfo: "none",
    showlegend: false
  });

  // Profile data points colored by depth
  traces.push({
    x: salinities,
    y: temps,
    mode: "markers",
    marker: {
      size: 7,
      color: pressures,
      colorscale: "Viridis",
      reversescale: true,
      colorbar: {
        title: { text: "Depth (dbar)", font: { color: "#f8fafc", size: 10 } },
        tickfont: { color: "#94a3b8", size: 9 },
        thickness: 12,
        len: 0.85
      }
    },
    text: hoverTexts,
    hoverinfo: "text",
    showlegend: false
  });

  const minS = Math.min(...salinities, 32.0);
  const maxS = Math.max(...salinities, 35.5);

  const layout = {
    xaxis: {
      title: { text: "Salinity (PSU)", font: { color: "#38bdf8", size: 11 } },
      range: [Math.floor(minS * 2) / 2 - 0.2, Math.ceil(maxS * 2) / 2 + 0.2],
      gridcolor: "#334155",
      tickfont: { color: "#f8fafc", size: 9 }
    },
    yaxis: {
      title: { text: "Temperature (°C)", font: { color: "#f43f5e", size: 11 } },
      gridcolor: "#334155",
      tickfont: { color: "#f8fafc", size: 9 }
    },
    margin: { l: 55, r: 20, t: 25, b: 45 }
  };

  renderPlotlyChart(simPlotlyChart, traces, layout);
}

function updateSimulatorHud(depth) {
  if (simHudDepth) simHudDepth.innerHTML = `${depth.toFixed(1)} <small>dbar</small>`;
  if (simDepthSlider) simDepthSlider.value = Math.round(depth);

  // Update Zone badge
  if (simZoneTag) {
    if (depth < 200) {
      simZoneTag.className = "zone-badge epipelagic";
      simZoneTag.textContent = "☀️ Sunlight Zone (0–200m)";
    } else if (depth < 1000) {
      simZoneTag.className = "zone-badge mesopelagic";
      simZoneTag.textContent = "🌒 Twilight Zone (200–1000m)";
    } else {
      simZoneTag.className = "zone-badge bathypelagic";
      simZoneTag.textContent = "🌌 Midnight Abyss (1000–2000m)";
    }
  }

  // Update Mission Phase badge
  if (simPhaseBadge) {
    let phaseText = "";
    let phaseClass = "phase-surface";
    if (simMissionPhase === 1) {
      phaseText = "📡 Phase 1: Surface GPS & Telemetry (0 dbar)";
      phaseClass = "phase-surface";
    } else if (simMissionPhase === 2) {
      phaseText = `⬇️ Phase 2: Descent to Parking Depth (${Math.round(depth)} dbar)`;
      phaseClass = "phase-descent";
    } else if (simMissionPhase === 3) {
      phaseText = `🌊 Phase 3: Isobaric Drift (1000 dbar Parking, Day 1–9)`;
      phaseClass = "phase-drift";
    } else if (simMissionPhase === 4) {
      phaseText = `⚓ Phase 4: Abyssal Dive to Profiling Depth (${Math.round(depth)} dbar)`;
      phaseClass = "phase-dive";
    } else if (simMissionPhase === 5) {
      phaseText = `🔬 Phase 5: Scientific Profiling Ascent (${Math.round(depth)} dbar, CTD sampling)`;
      phaseClass = "phase-ascent";
    }
    simPhaseBadge.className = `sim-phase-pill ${phaseClass}`;
    simPhaseBadge.textContent = phaseText;
  }

  // Interpolate in-situ measurements at current depth
  if (simProfileData && Array.isArray(simProfileData.levels) && simProfileData.levels.length > 0) {
    const levels = simProfileData.levels;
    let lower = levels[0], upper = levels[levels.length - 1];
    for (let i = 0; i < levels.length - 1; i++) {
      if (levels[i].pressure <= depth && levels[i + 1].pressure >= depth) {
        lower = levels[i];
        upper = levels[i + 1];
        break;
      }
    }
    const span = (upper.pressure - lower.pressure) || 1;
    const factor = Math.max(0, Math.min(1, (depth - lower.pressure) / span));

    const curTemp = lower.temperature != null && upper.temperature != null
      ? (lower.temperature + factor * (upper.temperature - lower.temperature))
      : (lower.temperature || upper.temperature);
    const curSal = lower.salinity != null && upper.salinity != null
      ? (lower.salinity + factor * (upper.salinity - lower.salinity))
      : (lower.salinity || upper.salinity);
    const curSpeed = lower.sound_speed != null && upper.sound_speed != null
      ? (lower.sound_speed + factor * (upper.sound_speed - lower.sound_speed))
      : (lower.sound_speed || upper.sound_speed);

    if (simHudTemp) simHudTemp.innerHTML = curTemp != null ? `${curTemp.toFixed(2)} <small>°C</small>` : "--";
    if (simHudSal) simHudSal.innerHTML = curSal != null ? `${curSal.toFixed(3)} <small>PSU</small>` : "--";
    if (simHudSpeed) simHudSpeed.innerHTML = curSpeed != null ? `${curSpeed.toFixed(1)} <small>m/s</small>` : "--";
  }

  // Relayout Plotly horizontal cursor without re-rendering whole chart
  if (simChartRendered && window.Plotly && simPlotlyChart && simPlotlyChart.layout) {
    try {
      const shapes = simPlotlyChart.layout.shapes || [];
      if (shapes.length >= 3) {
        Plotly.relayout(simPlotlyChart, {
          "shapes[2].y0": depth,
          "shapes[2].y1": depth
        });
      }
    } catch (_) {}
  }
}

function startSimAnimation() {
  if (simAnimId) cancelAnimationFrame(simAnimId);
  function loop() {
    renderOceanFrame();
    simAnimId = requestAnimationFrame(loop);
  }
  simAnimId = requestAnimationFrame(loop);
}

function renderOceanFrame() {
  if (!simCanvasCtx || !simOceanCanvas) return;
  const ctx = simCanvasCtx;
  const w = simOceanCanvas.width;
  const h = simOceanCanvas.height;

  // 1. Advance simulation state machine if playing
  if (simIsPlaying) {
    const rate = 1.6 * simSpeed;
    if (simMissionPhase === 1) {
      // Surface phase: stay 120 frames for GPS fix & radio telemetry
      simDriftFrames++;
      if (simDriftFrames > 120 / simSpeed) {
        simDriftFrames = 0;
        simMissionPhase = 2;
      }
    } else if (simMissionPhase === 2) {
      // Descent to 1000 dbar
      simDepth += rate * 2.2;
      if (simDepth >= 1000) {
        simDepth = 1000;
        simMissionPhase = 3;
        simDriftFrames = 0;
      }
    } else if (simMissionPhase === 3) {
      // Parking drift: stay ~180 frames at 1000 dbar drifting horizontally
      simDriftFrames++;
      if (simDriftFrames > 200 / simSpeed) {
        simDriftFrames = 0;
        simMissionPhase = 4;
      }
    } else if (simMissionPhase === 4) {
      // Abyssal dive to 2000 dbar
      simDepth += rate * 2.5;
      if (simDepth >= 2000) {
        simDepth = 2000;
        simMissionPhase = 5;
      }
    } else if (simMissionPhase === 5) {
      // Scientific profiling ascent 2000 -> 0 dbar
      simDepth -= rate * 1.8;
      if (simDepth <= 0) {
        simDepth = 0;
        simMissionPhase = 1;
        simDriftFrames = 0;
      }
    }
    updateSimulatorHud(simDepth);
  }

  // 2. Render oceanic water column gradient (Epipelagic -> Mesopelagic -> Bathypelagic Abyss)
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "#0284c7");     // Surface bright ocean blue
  grad.addColorStop(0.10, "#0369a1");  // 200m base of sunlight
  grad.addColorStop(0.40, "#1e1b4b");  // 800m twilight zone
  grad.addColorStop(0.60, "#0f172a");  // 1200m deep mesopelagic
  grad.addColorStop(1.0, "#020617");   // 2000m midnight abyss
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Surface water ripple & sunlight rays
  ctx.save();
  ctx.globalAlpha = 0.25;
  ctx.fillStyle = "#bae6fd";
  const now = Date.now() * 0.002;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  for (let x = 0; x <= w; x += 20) {
    ctx.lineTo(x, 8 + Math.sin(x * 0.05 + now) * 4);
  }
  ctx.lineTo(w, 0);
  ctx.closePath();
  ctx.fill();

  // Caustic sun shafts piercing top 120px
  ctx.globalAlpha = 0.08;
  const shaftGrad = ctx.createLinearGradient(0, 0, 0, 140);
  shaftGrad.addColorStop(0, "#ffffff");
  shaftGrad.addColorStop(1, "transparent");
  ctx.fillStyle = shaftGrad;
  ctx.beginPath();
  ctx.moveTo(40 + Math.sin(now) * 20, 0);
  ctx.lineTo(120 + Math.sin(now * 0.8) * 30, 130);
  ctx.lineTo(90 + Math.sin(now * 0.8) * 30, 130);
  ctx.lineTo(20 + Math.sin(now) * 20, 0);
  ctx.fill();
  ctx.restore();

  // 3. Render Depth Zone Boundaries & Physics Layers
  // MLD line
  if (simProfileData && simProfileData.mixed_layer_depth) {
    const mldY = (simProfileData.mixed_layer_depth / 2000) * (h - 70) + 35;
    ctx.save();
    ctx.strokeStyle = "rgba(56, 189, 248, 0.4)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(70, mldY);
    ctx.lineTo(w - 20, mldY);
    ctx.stroke();
    ctx.fillStyle = "rgba(56, 189, 248, 0.75)";
    ctx.font = "9px monospace";
    ctx.fillText(`MLD: ${simProfileData.mixed_layer_depth} dbar`, w - 100, mldY - 4);
    ctx.restore();
  }

  // Thermocline line
  if (simProfileData && simProfileData.thermocline_depth) {
    const thY = (simProfileData.thermocline_depth / 2000) * (h - 70) + 35;
    ctx.save();
    ctx.strokeStyle = "rgba(251, 146, 60, 0.4)";
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(70, thY);
    ctx.lineTo(w - 20, thY);
    ctx.stroke();
    ctx.fillStyle = "rgba(251, 146, 60, 0.8)";
    ctx.font = "9px monospace";
    ctx.fillText(`Thermocline Core: ${simProfileData.thermocline_depth} dbar`, w - 150, thY - 4);
    ctx.restore();
  }

  // SOFAR Sound Channel Axis (Acoustic Waveguide)
  if (simProfileData && simProfileData.sofar_depth) {
    const sofarY = (simProfileData.sofar_depth / 2000) * (h - 70) + 35;
    // Ambient sound channel waveguide glow
    ctx.save();
    const sofarGlow = ctx.createLinearGradient(0, sofarY - 25, 0, sofarY + 25);
    sofarGlow.addColorStop(0, "transparent");
    sofarGlow.addColorStop(0.5, "rgba(167, 139, 250, 0.15)");
    sofarGlow.addColorStop(1, "transparent");
    ctx.fillStyle = sofarGlow;
    ctx.fillRect(70, sofarY - 25, w - 90, 50);

    ctx.strokeStyle = "rgba(192, 132, 252, 0.65)";
    ctx.setLineDash([6, 3]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(70, sofarY);
    ctx.lineTo(w - 20, sofarY);
    ctx.stroke();

    ctx.fillStyle = "#c084fc";
    ctx.font = "10px monospace";
    ctx.fillText(`🔊 SOFAR Channel Axis (${simProfileData.sofar_depth} dbar)`, w - 195, sofarY - 6);
    ctx.restore();

    // Trigger acoustic sound rings in SOFAR channel
    if (Math.random() < 0.04) {
      simSonarRings.push({
        x: 180 + Math.random() * 50,
        y: sofarY,
        radius: 5,
        maxRadius: 120,
        alpha: 0.8
      });
    }
  }

  // 4. Update and draw acoustic sonar rings
  ctx.save();
  for (let i = simSonarRings.length - 1; i >= 0; i--) {
    const ring = simSonarRings[i];
    ring.radius += 1.8;
    ring.alpha -= 0.012;
    if (ring.alpha <= 0 || ring.radius >= ring.maxRadius) {
      simSonarRings.splice(i, 1);
      continue;
    }
    ctx.beginPath();
    // Elliptical acoustic waves propagating horizontally along waveguide
    ctx.ellipse(ring.x, ring.y, ring.radius * 1.6, ring.radius * 0.45, 0, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(192, 132, 252, ${ring.alpha.toFixed(2)})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.restore();

  // 5. Update and draw drifting marine snow / particles
  ctx.save();
  simParticles.forEach(p => {
    p.y += p.speedY;
    if (p.y > h) p.y = 0;
    const sway = Math.sin(now + p.y * p.swaySpeed) * p.swayAmp;
    const px = (p.baseX + sway) % w;
    ctx.fillStyle = `rgba(255, 255, 255, ${p.alpha.toFixed(2)})`;
    ctx.beginPath();
    ctx.arc(px, p.y, p.radius, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();

  // 6. Draw Robotic ARGO Float
  const floatY = (simDepth / 2000) * (h - 70) + 35;
  const floatX = w / 2 - 15;
  const bobbing = Math.sin(now * 2) * 2;
  const fy = floatY + bobbing;

  // Float Satellite Radio Telemetry Waves (Phase 1 / Surface)
  if (simDepth <= 20) {
    if (Math.random() < 0.12) {
      simRadioRings.push({ x: floatX + 10, y: fy - 22, r: 4, a: 0.9 });
    }
    ctx.save();
    for (let i = simRadioRings.length - 1; i >= 0; i--) {
      const rr = simRadioRings[i];
      rr.r += 1.4;
      rr.a -= 0.025;
      if (rr.a <= 0) {
        simRadioRings.splice(i, 1);
        continue;
      }
      ctx.beginPath();
      // Arc pointing upwards toward satellite
      ctx.arc(rr.x, rr.y, rr.r, Math.PI * 1.2, Math.PI * 1.8);
      ctx.strokeStyle = `rgba(52, 211, 153, ${rr.a.toFixed(2)})`;
      ctx.lineWidth = 1.8;
      ctx.stroke();
    }
    ctx.restore();
  }

  // Micro-bubbles rising
  if (simIsPlaying && Math.random() < 0.3) {
    simBubbles.push({
      x: floatX + 10 + (Math.random() * 8 - 4),
      y: fy + 38,
      r: Math.random() * 2 + 1,
      speed: Math.random() * 1.5 + 1,
      alpha: 0.7
    });
  }
  ctx.save();
  for (let i = simBubbles.length - 1; i >= 0; i--) {
    const b = simBubbles[i];
    b.y -= b.speed;
    b.alpha -= 0.015;
    if (b.y < 0 || b.alpha <= 0) {
      simBubbles.splice(i, 1);
      continue;
    }
    ctx.fillStyle = `rgba(224, 242, 254, ${b.alpha.toFixed(2)})`;
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  // Draw ARGO Float Body:
  ctx.save();
  // Antenna rod on top
  ctx.strokeStyle = "#94a3b8";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(floatX + 10, fy);
  ctx.lineTo(floatX + 10, fy - 22);
  ctx.stroke();

  // Antenna LED tip
  const ledBlink = Math.sin(now * 6) > 0;
  const ledColor = (simDepth <= 25)
    ? (ledBlink ? "#10b981" : "#047857")
    : (simMissionPhase === 3 ? "#f59e0b" : "#60a5fa");
  ctx.fillStyle = ledColor;
  ctx.beginPath();
  ctx.arc(floatX + 10, fy - 22, 3, 0, Math.PI * 2);
  ctx.fill();

  // Main cylindrical pressure hull (Oceanographic Yellow)
  const hullGrad = ctx.createLinearGradient(floatX, fy, floatX + 20, fy);
  hullGrad.addColorStop(0, "#fbbf24");
  hullGrad.addColorStop(0.3, "#fef08a");
  hullGrad.addColorStop(0.7, "#f59e0b");
  hullGrad.addColorStop(1, "#d97706");
  ctx.fillStyle = hullGrad;
  ctx.beginPath();
  ctx.roundRect(floatX, fy, 20, 46, [5, 5, 4, 4]);
  ctx.fill();

  // Collar and CTD sensor head band
  ctx.fillStyle = "#334155";
  ctx.fillRect(floatX - 1, fy + 14, 22, 5);

  // Hydraulic bladder at bottom (expands on ascent, deflates on descent)
  const bladderExpansion = (simMissionPhase === 5 || simDepth <= 20) ? 6 : 2;
  ctx.fillStyle = "#1e293b";
  ctx.beginPath();
  ctx.arc(floatX + 10, fy + 46, 5 + bladderExpansion, 0, Math.PI);
  ctx.fill();
  ctx.strokeStyle = "#475569";
  ctx.lineWidth = 1;
  ctx.stroke();

  // High-precision CTD conductivity cell on side
  ctx.fillStyle = "#0284c7";
  ctx.fillRect(floatX + 15, fy + 4, 6, 8);

  // Float Platform Label tag
  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  ctx.font = "bold 10px monospace";
  ctx.fillText(simCurrentFloat || "ARGO", floatX + 26, fy + 26);
  ctx.font = "9px sans-serif";
  ctx.fillStyle = "#94a3b8";
  ctx.fillText(`${simDepth.toFixed(0)} dbar`, floatX + 26, fy + 38);

  ctx.restore();
}

// Simulator Control Listeners
simFloatSelect?.addEventListener("change", () => {
  if (simFloatSelect.value) {
    loadDiveProfile(simFloatSelect.value);
  }
});

simLoadBtn?.addEventListener("click", () => {
  if (simFloatSelect.value) {
    loadDiveProfile(simFloatSelect.value);
  }
});

simPlayBtn?.addEventListener("click", () => {
  simIsPlaying = !simIsPlaying;
  if (simPlayBtn) {
    simPlayBtn.textContent = simIsPlaying ? "⏸ Pause Dive" : "▶ Resume Dive";
    simPlayBtn.classList.toggle("primary", !simIsPlaying);
  }
});

simResetBtn?.addEventListener("click", () => {
  simDepth = 0.0;
  simMissionPhase = 1;
  simDriftFrames = 0;
  simIsPlaying = false;
  if (simPlayBtn) {
    simPlayBtn.textContent = "▶ Start Dive";
    simPlayBtn.classList.add("primary");
  }
  updateSimulatorHud(0);
});

simSpeedBtns?.forEach(btn => {
  btn.addEventListener("click", () => {
    simSpeedBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    simSpeed = Number(btn.dataset.speed) || 1;
  });
});

simDepthSlider?.addEventListener("input", (e) => {
  simDepth = parseFloat(e.target.value) || 0.0;
  if (simDepth < 20) simMissionPhase = 1;
  else if (simDepth < 1000) simMissionPhase = 2;
  else if (simDepth === 1000) simMissionPhase = 3;
  else if (simDepth < 2000) simMissionPhase = 4;
  else simMissionPhase = 5;
  updateSimulatorHud(simDepth);
});

// ── Interactive Geospatial Ocean Map (Leaflet.js) ─────────────────────────────
let oceanLeafletMap = null;
let mapMarkersLayer = null;
let mapLinesLayer = null;
let mapBaseLayers = {};
let mapShowLines = true;
let mapPointsData = [];
let mapInitialized = false;

function getTempColor(t) {
  if (t === null || t === undefined) return "#94a3b8"; // slate
  if (t < 26.0) return "#38bdf8";                      // bright sky blue
  if (t < 28.0) return "#34d399";                      // emerald
  if (t < 29.0) return "#f59e0b";                      // amber
  return "#f43f5e";                                    // rose / red
}

async function initOceanMap() {
  if (typeof L === "undefined") {
    if (mapStatsText) mapStatsText.textContent = "Leaflet mapping library loading...";
    return;
  }

  if (!oceanLeafletMap) {
    const mapEl = document.getElementById("ocean-leaflet-map");
    if (!mapEl) return;

    oceanLeafletMap = L.map("ocean-leaflet-map", {
      center: [13.5, 87.5],
      zoom: 5,
      minZoom: 3,
      maxZoom: 13,
      attributionControl: false
    });

    // Basemaps (High-reliability ESRI Oceanographic & Geospatial layers - no API key watermarks or 403 blocks)
    mapBaseLayers.ocean = L.layerGroup([
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 13,
        attribution: "ESRI Ocean / GEBCO"
      }),
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 13
      })
    ]);

    mapBaseLayers.dark = L.layerGroup([
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 16,
        attribution: "ESRI Dark Canvas"
      }),
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 16
      })
    ]);

    mapBaseLayers.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 18,
      attribution: "ESRI World Imagery"
    });

    mapBaseLayers.topo = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 18,
      attribution: "ESRI World Topo"
    });
    mapBaseLayers.osm = mapBaseLayers.topo;

    mapBaseLayers.ocean.addTo(oceanLeafletMap);

    mapMarkersLayer = L.layerGroup().addTo(oceanLeafletMap);
    mapLinesLayer = L.layerGroup().addTo(oceanLeafletMap);

    // Add bathymetry legend
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = function() {
      const div = L.DomUtil.create("div", "map-legend-box");
      div.style.background = "rgba(15, 23, 42, 0.9)";
      div.style.padding = "8px 12px";
      div.style.borderRadius = "6px";
      div.style.border = "1px solid #334155";
      div.style.fontSize = "11px";
      div.style.color = "#f8fafc";
      div.style.lineHeight = "1.5";
      div.innerHTML = `
        <div style="font-weight:600; margin-bottom:4px; color:#38bdf8;">Sea Surface Temp</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#38bdf8;margin-right:6px;"></span> &lt; 26°C</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#34d399;margin-right:6px;"></span> 26°C – 28°C</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;margin-right:6px;"></span> 28°C – 29°C</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f43f5e;margin-right:6px;"></span> &gt; 29°C</div>
      `;
      return div;
    };
    legend.addTo(oceanLeafletMap);

    // Listeners
    mapBasemapSelect?.addEventListener("change", (e) => {
      const selected = e.target.value;
      Object.values(mapBaseLayers).forEach(layer => oceanLeafletMap.removeLayer(layer));
      if (mapBaseLayers[selected]) {
        mapBaseLayers[selected].addTo(oceanLeafletMap);
      }
    });

    mapToggleLines?.addEventListener("click", () => {
      mapShowLines = !mapShowLines;
      mapToggleLines.classList.toggle("active", mapShowLines);
      if (mapLinesLayer) {
        if (mapShowLines) oceanLeafletMap.addLayer(mapLinesLayer);
        else oceanLeafletMap.removeLayer(mapLinesLayer);
      }
    });

    mapResetBtn?.addEventListener("click", () => {
      if (mapFloatFilter) mapFloatFilter.value = "";
      if (mapYearFilter) mapYearFilter.value = "";
      if (mapFloatCard) mapFloatCard.style.display = "none";
      oceanLeafletMap.setView([13.5, 87.5], 5);
      loadMapPoints();
    });

    mapFloatFilter?.addEventListener("change", () => loadMapPoints());
    mapYearFilter?.addEventListener("change", () => loadMapPoints());
    mapCardClose?.addEventListener("click", () => {
      if (mapFloatCard) mapFloatCard.style.display = "none";
    });
  }

  setTimeout(() => {
    if (oceanLeafletMap) {
      oceanLeafletMap.invalidateSize();
    }
  }, 100);

  if (!mapInitialized) {
    mapInitialized = true;
    await loadMapPoints();
  }
}

async function loadMapPoints() {
  if (!oceanLeafletMap || !mapMarkersLayer || !mapLinesLayer) return;

  const selectedFloat = mapFloatFilter?.value || "";
  const selectedYear = mapYearFilter?.value || "";

  if (mapStatsText) mapStatsText.textContent = "Loading observations...";

  let url = `${ENDPOINTS.mapPoints}?limit=2000`;
  if (selectedFloat) url += `&platform=${encodeURIComponent(selectedFloat)}`;
  if (selectedYear) url += `&year=${encodeURIComponent(selectedYear)}`;

  try {
    const res = await fetch(url, { headers: authHeaders() });
    if (!res.ok) throw new Error("Failed to load map data");
    const data = await res.json();
    mapPointsData = data.points || [];

    // Populate platforms filter if empty
    if (mapFloatFilter && mapFloatFilter.options.length <= 1 && data.platforms) {
      data.platforms.forEach(plat => {
        const opt = document.createElement("option");
        opt.value = plat;
        opt.textContent = `Float #${plat}`;
        mapFloatFilter.appendChild(opt);
      });
    }

    renderMapData(mapPointsData, selectedFloat);
  } catch (err) {
    if (mapStatsText) mapStatsText.textContent = "Error loading map points";
    console.error("Map data error:", err);
  }
}

function renderMapData(points, selectedFloat) {
  mapMarkersLayer.clearLayers();
  mapLinesLayer.clearLayers();

  if (!points || !points.length) {
    if (mapStatsText) mapStatsText.textContent = "No profiles found for filter";
    return;
  }

  // Group by platform for trajectories
  const byPlatform = {};
  points.forEach(pt => {
    if (!byPlatform[pt.platform]) byPlatform[pt.platform] = [];
    byPlatform[pt.platform].push(pt);
  });

  const distinctFloats = Object.keys(byPlatform).length;
  if (mapStatsText) {
    mapStatsText.textContent = `Showing ${points.length.toLocaleString()} Profiles across ${distinctFloats} Floats`;
  }

  const bounds = L.latLngBounds();

  // Draw trajectory drift lines
  Object.entries(byPlatform).forEach(([plat, pts]) => {
    if (pts.length >= 2) {
      const latlngs = pts.map(p => [p.lat, p.lon]);
      const isTarget = selectedFloat && selectedFloat === plat;
      const poly = L.polyline(latlngs, {
        color: isTarget ? "#38bdf8" : "rgba(56, 189, 248, 0.45)",
        weight: isTarget ? 3 : 1.5,
        dashArray: isTarget ? null : "3, 4"
      });
      mapLinesLayer.addLayer(poly);
    }
  });

  // Draw circle markers
  points.forEach((pt) => {
    const latlng = [pt.lat, pt.lon];
    bounds.extend(latlng);

    const isLastForFloat = byPlatform[pt.platform] && byPlatform[pt.platform][byPlatform[pt.platform].length - 1] === pt;
    const color = getTempColor(pt.surface_temp);

    const marker = L.circleMarker(latlng, {
      radius: isLastForFloat ? 7 : 4.5,
      color: isLastForFloat ? "#f8fafc" : "#0f172a",
      weight: isLastForFloat ? 2 : 1,
      fillColor: color,
      fillOpacity: 0.85
    });

    marker.bindTooltip(`<strong>Float #${pt.platform}</strong><br/>${pt.timestamp ? pt.timestamp.substring(0, 10) : ''}`, {
      direction: "top",
      offset: [0, -5]
    });

    marker.on("click", () => {
      showMapFloatCard(pt);
    });

    mapMarkersLayer.addLayer(marker);
  });

  if (selectedFloat && bounds.isValid()) {
    oceanLeafletMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 });
  }
}

function showMapFloatCard(pt) {
  if (!mapFloatCard || !mapCardPlatform || !mapCardBody) return;

  mapCardPlatform.textContent = `Float #${pt.platform}`;
  mapCardBody.innerHTML = `
    <div class="map-card-row">
      <span class="map-card-label">Profile ID</span>
      <span class="map-card-val">${escapeHtml(pt.id)}</span>
    </div>
    <div class="map-card-row">
      <span class="map-card-label">Date & Time</span>
      <span class="map-card-val">${pt.timestamp ? pt.timestamp.substring(0, 19).replace('T', ' ') : 'N/A'}</span>
    </div>
    <div class="map-card-row">
      <span class="map-card-label">Coordinates</span>
      <span class="map-card-val">${pt.lat.toFixed(3)}°N, ${pt.lon.toFixed(3)}°E</span>
    </div>
    <div class="map-card-row">
      <span class="map-card-label">Surface Temp</span>
      <span class="map-card-val" style="color:#38bdf8">${pt.surface_temp !== null ? pt.surface_temp.toFixed(2) + ' °C' : 'N/A'}</span>
    </div>
    <div class="map-card-row">
      <span class="map-card-label">Surface Salinity</span>
      <span class="map-card-val" style="color:#34d399">${pt.surface_sal !== null ? pt.surface_sal.toFixed(2) + ' PSU' : 'N/A'}</span>
    </div>
    <div class="map-card-row">
      <span class="map-card-label">Max Depth</span>
      <span class="map-card-val">${pt.max_depth !== null ? pt.max_depth.toFixed(0) + ' dbar' : 'N/A'}</span>
    </div>
    <div class="map-card-actions">
      <button class="map-card-btn primary" id="map-inspect-dive-btn">🤿 Dive Profile</button>
      <button class="map-card-btn" id="map-ask-chat-btn">💬 Ask in Chat</button>
    </div>
  `;

  document.getElementById("map-inspect-dive-btn")?.addEventListener("click", () => {
    switchTab("simulator");
    if (simFloatSelect) {
      simFloatSelect.value = pt.platform;
      loadSimulatorProfile(pt.platform);
    }
  });

  document.getElementById("map-ask-chat-btn")?.addEventListener("click", () => {
    switchTab("chat");
    if (questionInput) {
      questionInput.value = `Show temperature profiles for float ${pt.platform}`;
      questionInput.focus();
    }
  });

  mapFloatCard.style.display = "block";
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (str == null || str === "") return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function flashBtn(btn, text) {
  if (!btn) return;
  const orig = btn.innerHTML;
  btn.textContent = text;
  setTimeout(() => btn.innerHTML = orig, 1800);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
const _sharedToken = new URLSearchParams(window.location.search).get("share");
if (_sharedToken) { showSharedChat(_sharedToken); } else { checkAuth(); }