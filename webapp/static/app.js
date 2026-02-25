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

// Poll video status (English + Chinese) and refresh card when ready
document.body.addEventListener("htmx:afterRequest", function (evt) {
  if (!evt.detail.xhr) return;
  var url = evt.detail.xhr.responseURL || "";

  // Segment video polling
  var isVideoStatus = url.indexOf("/video/status") !== -1 || url.indexOf("/video-zh/status") !== -1;
  // Video curation pipeline polling
  var isAnglesStatus = url.indexOf("/angles/status") !== -1;
  var isCurationStatus = url.indexOf("/curation/status") !== -1;
  var isCuratedVideoStatus = url.indexOf("/curated-video/status") !== -1;
  var isPublishStatus = url.indexOf("/curated-video/publish-status") !== -1;

  if (!isVideoStatus && !isAnglesStatus && !isCurationStatus && !isCuratedVideoStatus && !isPublishStatus) return;

  try {
    var data = JSON.parse(evt.detail.xhr.responseText);

    if (isCuratedVideoStatus) {
      // Curated video: check both Chinese and English statuses
      var zhDone = !data.status || data.status === "ready" || data.status === "failed" || data.status === "pending";
      var enDone = !data.en_status || data.en_status === "ready" || data.en_status === "failed" || data.en_status === "pending";
      var anyChanged = data.status === "ready" || data.status === "failed" || data.en_status === "ready" || data.en_status === "failed";
      if (anyChanged && zhDone && enDone) {
        window.location.reload();
      }
    } else if (data.status === "ready" || data.status === "failed" || data.status === "published") {
      // Reload the page to show the updated state
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
