/* 100Baggers Review - HTMX config + editor helpers */

// Show save feedback on successful HTMX swaps
document.body.addEventListener("htmx:afterSwap", function (evt) {
  // Flash the target briefly to indicate success
  var target = evt.detail.target;
  if (target) {
    target.classList.add("htmx-settled");
    setTimeout(function () {
      target.classList.remove("htmx-settled");
    }, 1000);
  }
});

// Poll video status and refresh card when video is ready
document.body.addEventListener("htmx:afterRequest", function (evt) {
  if (!evt.detail.xhr) return;
  var url = evt.detail.xhr.responseURL || "";
  if (url.indexOf("/video/status") === -1) return;

  try {
    var data = JSON.parse(evt.detail.xhr.responseText);
    if (data.status === "ready" || data.status === "failed") {
      // Reload the page to show the updated video state
      window.location.reload();
    }
  } catch (e) {
    // ignore parse errors
  }
});

// Create Session: show loading spinner on submit
document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("create-session-form");
  if (form) {
    form.addEventListener("submit", function () {
      var btn = document.getElementById("create-session-btn");
      if (btn) {
        btn.setAttribute("aria-busy", "true");
        btn.textContent = "Generating content...";
        btn.disabled = true;
      }
    });
  }
});

// Auto-resize textareas
document.addEventListener("input", function (evt) {
  if (evt.target.tagName === "TEXTAREA" && evt.target.classList.contains("content-editor")) {
    evt.target.style.height = "auto";
    evt.target.style.height = evt.target.scrollHeight + "px";
  }
});

// Initialize textarea heights on page load
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("textarea.content-editor").forEach(function (ta) {
    ta.style.height = "auto";
    ta.style.height = ta.scrollHeight + "px";
  });
});
