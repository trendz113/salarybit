/**
 * SalaryBit site-wide widgets
 * ---------------------------
 * Include with: <script src="/assets/js/site-widgets.js"></script>
 * right before </body> on any page.
 *
 * Adds two things, self-contained (inline styles, no dependency on the
 * host page's own CSS/theme, so it looks consistent everywhere):
 *
 * 1. A floating "Home" button — but ONLY if the page doesn't already
 *    have a link back to "/" somewhere in a nav/header. Auto-detects,
 *    so the same script works whether or not the page already has one.
 *
 * 2. A floating "Feedback" button (bottom-right) that opens a small
 *    panel for reporting an issue or suggestion. Posts to
 *    /api/site-feedback on the Railway backend.
 */
(function () {
  var API_BASE = "https://web-production-456eb.up.railway.app";

  function alreadyHasHomeLink() {
    var candidates = document.querySelectorAll(
      'nav a[href="/"], nav a[href="https://salarybit.in/"], nav a[href="https://salarybit.in"], ' +
      '.nav a[href="/"], .brand[href="/"], header a[href="/"]'
    );
    return candidates.length > 0;
  }

  function injectHomeButton() {
    if (alreadyHasHomeLink()) return;
    var a = document.createElement("a");
    a.href = "/";
    a.setAttribute("aria-label", "Back to SalaryBit home");
    a.textContent = "← SalaryBit";
    a.style.cssText = [
      "position:fixed", "top:14px", "left:14px", "z-index:9998",
      "background:rgba(26,26,46,0.92)", "color:#fff",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "font-size:13px", "font-weight:600", "text-decoration:none",
      "padding:7px 14px", "border-radius:999px",
      "box-shadow:0 2px 10px rgba(0,0,0,.18)",
      "backdrop-filter:blur(6px)", "transition:opacity .15s,transform .15s",
      "opacity:0.88"
    ].join(";");
    a.onmouseover = function () { a.style.opacity = "1"; a.style.transform = "translateY(-1px)"; };
    a.onmouseout = function () { a.style.opacity = "0.88"; a.style.transform = "translateY(0)"; };
    document.body.appendChild(a);
  }

  function injectFeedbackWidget() {
    var btn = document.createElement("button");
    btn.setAttribute("aria-label", "Report an issue or suggestion");
    btn.innerHTML = "💬";
    btn.style.cssText = [
      "position:fixed", "bottom:18px", "right:18px", "z-index:9998",
      "width:48px", "height:48px", "border-radius:50%", "border:none",
      "background:linear-gradient(135deg,#5b6af0,#0ea5a0)", "color:#fff",
      "font-size:20px", "cursor:pointer",
      "box-shadow:0 4px 16px rgba(91,106,240,.35)",
      "display:flex", "align-items:center", "justify-content:center",
      "transition:transform .15s"
    ].join(";");
    btn.onmouseover = function () { btn.style.transform = "scale(1.06)"; };
    btn.onmouseout = function () { btn.style.transform = "scale(1)"; };

    var panel = document.createElement("div");
    panel.style.cssText = [
      "position:fixed", "bottom:76px", "right:18px", "z-index:9999",
      "width:min(320px, calc(100vw - 36px))", "background:#fff",
      "border-radius:14px", "box-shadow:0 8px 32px rgba(0,0,0,.22)",
      "padding:16px", "display:none",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
    ].join(";");
    panel.innerHTML =
      '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:4px;">Found an issue, or have a suggestion?</div>' +
      '<div style="font-size:12px;color:#7b7b9d;margin-bottom:10px;">Tell us what happened — we read every one of these.</div>' +
      '<input id="sb-fb-email" type="email" placeholder="Your email" style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:8px;border:1.5px solid #e2e2f0;border-radius:8px;font-size:13px;font-family:inherit;">' +
      '<textarea id="sb-fb-message" placeholder="What went wrong, or what should we add?" rows="3" style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:8px;border:1.5px solid #e2e2f0;border-radius:8px;font-size:13px;font-family:inherit;resize:vertical;"></textarea>' +
      '<button id="sb-fb-submit" style="width:100%;height:38px;background:linear-gradient(135deg,#5b6af0,#0ea5a0);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;">Send</button>' +
      '<div id="sb-fb-msg" style="font-size:12px;margin-top:8px;"></div>';

    document.body.appendChild(btn);
    document.body.appendChild(panel);

    var open = false;
    btn.addEventListener("click", function () {
      open = !open;
      panel.style.display = open ? "block" : "none";
    });

    panel.querySelector("#sb-fb-submit").addEventListener("click", function () {
      var emailInput = panel.querySelector("#sb-fb-email");
      var msgInput = panel.querySelector("#sb-fb-message");
      var statusEl = panel.querySelector("#sb-fb-msg");
      var submitBtn = panel.querySelector("#sb-fb-submit");
      var email = emailInput.value.trim();
      var message = msgInput.value.trim();

      if (!email || email.indexOf("@") === -1) {
        statusEl.style.color = "#e05c5c";
        statusEl.textContent = "Please enter a valid email.";
        return;
      }
      if (!message) {
        statusEl.style.color = "#e05c5c";
        statusEl.textContent = "Please enter your issue or suggestion.";
        return;
      }

      submitBtn.disabled = true;
      submitBtn.textContent = "Sending...";
      statusEl.textContent = "";

      fetch(API_BASE + "/api/site-feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, message: message, page_url: window.location.href })
      })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
          if (result.ok) {
            statusEl.style.color = "#16a34a";
            statusEl.textContent = "Thank you — we'll take a look.";
            emailInput.value = "";
            msgInput.value = "";
            submitBtn.style.display = "none";
          } else {
            statusEl.style.color = "#e05c5c";
            statusEl.textContent = (result.data && result.data.error) || "Something went wrong. Please try again.";
            submitBtn.disabled = false;
            submitBtn.textContent = "Send";
          }
        })
        .catch(function () {
          statusEl.style.color = "#e05c5c";
          statusEl.textContent = "Network error — please try again.";
          submitBtn.disabled = false;
          submitBtn.textContent = "Send";
        });
    });
  }

  function init() {
    injectHomeButton();
    injectFeedbackWidget();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
