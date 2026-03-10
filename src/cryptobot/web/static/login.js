function setAccountMsg(msg, ok = true) {
  const color = ok ? "#86efac" : "#fca5a5";
  ["account-msg", "forgot-msg"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.textContent = msg;
    node.style.color = color;
  });
}

function setButtonsBusy(busy, activeButtonId = null, busyLabel = "Please wait...") {
  const ids = ["signup-btn", "login-btn", "google-btn", "forgot-btn", "forgot-send-btn", "forgot-cancel-btn"];
  ids.forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    if (!btn.dataset.defaultLabel) btn.dataset.defaultLabel = btn.textContent || "";
    btn.disabled = busy;
    btn.classList.toggle("btn-loading", busy && id === activeButtonId);
    btn.textContent = busy && id === activeButtonId ? busyLabel : btn.dataset.defaultLabel;
  });
}

function showPanel(mode) {
  const auth = document.getElementById("auth-panel");
  const forgot = document.getElementById("forgot-panel");
  if (!auth || !forgot) return;
  auth.style.display = mode === "auth" ? "block" : "none";
  forgot.style.display = mode === "forgot" ? "block" : "none";
}

async function signup() {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  const response = await fetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Signup failed");
  setAccountMsg("Signup successful. Check your email verification link.", true);
}

async function login() {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Login failed");
  window.location.href = "/app";
}

async function directResetPassword() {
  const email = (document.getElementById("forgot-email")?.value || "").trim();
  const newPassword = document.getElementById("forgot-new-password")?.value || "";
  const confirmPassword = document.getElementById("forgot-confirm-password")?.value || "";

  if (!email) throw new Error("Enter your email");
  if (newPassword.length < 8) throw new Error("Password must be at least 8 characters");
  if (newPassword !== confirmPassword) throw new Error("Passwords do not match");

  const response = await fetch("/api/auth/forgot-password", {
    cache: "no-store",
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Password reset failed");
  setAccountMsg(data.message || "Password reset successful. You can now login.", true);
}

function loginWithGoogle() {
  setButtonsBusy(true, "google-btn", "Redirecting...");
  setAccountMsg("Opening Google sign-in...", true);
  window.location.href = "/auth/google/login";
}

function bindPasswordToggles() {
  document.querySelectorAll(".pw-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      const input = targetId ? document.getElementById(targetId) : null;
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "🙈" : "👁";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
}

window.addEventListener("DOMContentLoaded", () => {
  bindPasswordToggles();

  document.getElementById("signup-btn")?.addEventListener("click", async () => {
    setButtonsBusy(true, "signup-btn", "Signing up...");
    setAccountMsg("Creating your account...", true);
    try {
      await signup();
    } catch (err) {
      setAccountMsg(String(err), false);
    } finally {
      setButtonsBusy(false);
    }
  });

  document.getElementById("login-btn")?.addEventListener("click", async () => {
    setButtonsBusy(true, "login-btn", "Logging in...");
    setAccountMsg("Signing you in...", true);
    try {
      await login();
    } catch (err) {
      setAccountMsg(String(err), false);
      setButtonsBusy(false);
    }
  });

  document.getElementById("google-btn")?.addEventListener("click", loginWithGoogle);

  document.getElementById("forgot-btn")?.addEventListener("click", () => {
    const authEmail = document.getElementById("auth-email")?.value || "";
    const forgotEmail = document.getElementById("forgot-email");
    if (forgotEmail && authEmail) forgotEmail.value = authEmail;
    showPanel("forgot");
    setAccountMsg("Set your new password.", true);
  });

  document.getElementById("forgot-cancel-btn")?.addEventListener("click", () => {
    showPanel("auth");
    setAccountMsg("Create account, verify email, then login.", true);
  });

  const runDirectReset = async (e) => {
    if (e) e.preventDefault();
    setButtonsBusy(true, "forgot-send-btn", "Resetting...");
    setAccountMsg("Updating password...", true);
    try {
      await directResetPassword();
      showPanel("auth");
    } catch (err) {
      setAccountMsg(String(err), false);
    } finally {
      setButtonsBusy(false);
    }
  };

  document.getElementById("forgot-send-btn")?.addEventListener("click", runDirectReset);
  document.getElementById("forgot-panel")?.addEventListener("submit", runDirectReset);
});
