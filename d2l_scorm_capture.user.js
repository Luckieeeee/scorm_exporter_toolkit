// ==UserScript==
// @name         D2L SCORM Capture
// @namespace    https://github.com/
// @version      0.1.6
// @description  Capture Articulate Rise / SCORM course JSON from a logged-in D2L content page.
// @match        https://d2l.ucalgary.ca/d2l/lms/content/viewer/*
// @match        https://*/d2l/lms/content/viewer/*
// @run-at       document-idle
// @noframes
// @grant        GM_registerMenuCommand
// ==/UserScript==

(function installD2LScormCapture() {
  "use strict";

  const isD2LPage =
    /(^|\.)d2l\./i.test(window.location.hostname) ||
    window.location.hostname === "d2l.ucalgary.ca" ||
    window.location.pathname.includes("/d2l/");

  if (!isD2LPage) return;
  if (window.top !== window) return;

  const BUTTON_ID = "scorm-exporter-capture-button";
  const STATUS_ID = "scorm-exporter-capture-status";
  const WRAPPER_ID = "scorm-exporter-capture-wrapper";
  let captureInProgress = false;

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function slugify(value) {
    return String(value || "course")
      .replace(/[^A-Za-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 80) || "course";
  }

  function collectTextFromFrames(rootWindow) {
    const parts = [];
    const seen = new Set();

    function visit(win, label) {
      try {
        if (!win || seen.has(win)) return;
        seen.add(win);

        const doc = win.document;
        if (!doc) return;

        parts.push("\n\n==== " + (label || doc.URL || "frame") + " ====\n");
        parts.push(doc.documentElement ? doc.documentElement.textContent || "" : "");

        for (let i = 0; i < win.frames.length; i += 1) {
          visit(win.frames[i], (label || "top") + " > frame " + (i + 1));
        }
      } catch (error) {
        parts.push("\n[skipped inaccessible frame: " + error.message + "]\n");
      }
    }

    visit(rootWindow, "top");
    return parts.join("\n");
  }

  function decodeCourseFromText(text) {
    const patterns = [
      /__fetchCourse\(\)\s*\{[\s\S]*?deserialize\("([A-Za-z0-9+/=]+)"\)/,
      /deserialize\("([A-Za-z0-9+/=]{1000,})"\)/,
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (!match) continue;

      const binary = atob(match[1]);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const jsonText = new TextDecoder("utf-8").decode(bytes);
      const data = JSON.parse(jsonText);
      if (!data.course) {
        throw new Error("Decoded payload did not contain a top-level course object.");
      }
      return { jsonText, data };
    }

    throw new Error("No embedded Rise/SCORM deserialize payload was found.");
  }

  function downloadFile(filename, text, type) {
    const blob = new Blob([text], { type: type || "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function tidFromLocation() {
    try {
      return new URL(window.location.href).searchParams.get("tid") || "unknown_tid";
    } catch {
      return "unknown_tid";
    }
  }

  function setStatus(message, isError) {
    const status = document.getElementById(STATUS_ID);
    if (!status) return;
    status.textContent = message;
    status.style.background = isError ? "#7f1d1d" : "#164e63";
  }

  async function captureCourse() {
    if (captureInProgress) return;
    captureInProgress = true;

    try {
      const button = document.getElementById(BUTTON_ID);
      if (button) {
        button.disabled = true;
        button.textContent = "Capturing...";
      }
      setStatus("Looking for SCORM payload...", false);

      let decoded = null;
      let lastError = null;

      for (let attempt = 1; attempt <= 12; attempt += 1) {
        const payloadText = collectTextFromFrames(window);
        try {
          decoded = decodeCourseFromText(payloadText);
          break;
        } catch (error) {
          lastError = error;
          setStatus("Waiting for SCORM payload... attempt " + attempt + "/12", false);
          await wait(1000);
        }
      }

      if (!decoded) {
        throw lastError || new Error("Could not capture the SCORM payload.");
      }

      const course = decoded.data.course;
      const title = course.title || document.title || "SCORM Course";
      const tid = tidFromLocation();
      const stem = tid + "_" + slugify(title);
      const metadata = {
        title,
        tid,
        sourceUrl: window.location.href,
        capturedAt: new Date().toISOString(),
        lessonRecords: Array.isArray(course.lessons) ? course.lessons.length : 0,
      };

      downloadFile(stem + "_course.json", decoded.jsonText, "application/json;charset=utf-8");
      downloadFile(stem + "_capture_metadata.json", JSON.stringify(metadata, null, 2), "application/json;charset=utf-8");
      setStatus("Captured " + metadata.lessonRecords + " lesson records.", false);
    } finally {
      captureInProgress = false;
    }
  }

  async function runCaptureFromMenu() {
    try {
      await captureCourse();
    } catch (error) {
      alert("SCORM capture failed: " + error.message);
      console.error(error);
    }
  }

  function injectControls() {
    if (document.getElementById(BUTTON_ID)) return;
    if (!document.body) return;

    const wrapper = document.createElement("div");
    wrapper.id = WRAPPER_ID;
    wrapper.style.position = "fixed";
    wrapper.style.right = "16px";
    wrapper.style.bottom = "16px";
    wrapper.style.zIndex = "2147483647";
    wrapper.style.display = "flex";
    wrapper.style.flexDirection = "column";
    wrapper.style.alignItems = "flex-end";
    wrapper.style.gap = "8px";
    wrapper.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";

    const status = document.createElement("div");
    status.id = STATUS_ID;
    status.textContent = "Ready";
    status.style.maxWidth = "260px";
    status.style.padding = "7px 10px";
    status.style.borderRadius = "6px";
    status.style.background = "#164e63";
    status.style.color = "#fff";
    status.style.fontSize = "12px";
    status.style.boxShadow = "0 8px 24px rgba(0,0,0,0.22)";
    status.style.display = "none";

    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
    button.textContent = "Capture SCORM";
    button.title = "Capture SCORM from this D2L page";
    button.style.border = "0";
    button.style.borderRadius = "6px";
    button.style.padding = "10px 14px";
    button.style.background = "#0f766e";
    button.style.color = "#fff";
    button.style.fontSize = "14px";
    button.style.fontWeight = "700";
    button.style.cursor = "pointer";
    button.style.boxShadow = "0 8px 24px rgba(0,0,0,0.22)";

    button.addEventListener("click", async () => {
      status.style.display = "block";
      try {
        await captureCourse();
      } catch (error) {
        setStatus("Capture failed: " + error.message, true);
        console.error(error);
      } finally {
        button.disabled = false;
        button.textContent = "Capture SCORM";
      }
    });

    wrapper.append(status, button);
    document.body.appendChild(wrapper);
  }

  function startInjectionLoop() {
    if (typeof GM_registerMenuCommand === "function") {
      GM_registerMenuCommand("Capture current D2L SCORM", runCaptureFromMenu);
    }
    injectControls();

    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      if (!document.getElementById(WRAPPER_ID)) {
        injectControls();
      }
      if (document.getElementById(WRAPPER_ID) || attempts >= 20) {
        clearInterval(interval);
      }
    }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startInjectionLoop, { once: true });
  } else {
    startInjectionLoop();
  }
})();
