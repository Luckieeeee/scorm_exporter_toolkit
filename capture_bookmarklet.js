/*
 * D2L / Articulate Rise SCORM capture helper.
 *
 * Use this from a logged-in browser tab that is displaying the D2L content
 * viewer. It reads the embedded Rise course payload from accessible frames and
 * downloads a decoded course.json file. Nothing is uploaded anywhere.
 */
(async function captureD2LRiseCourse() {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

  let decoded = null;
  let payloadText = "";
  let lastError = null;

  for (let attempt = 1; attempt <= 12; attempt += 1) {
    payloadText = collectTextFromFrames(window);
    try {
      decoded = decodeCourseFromText(payloadText);
      break;
    } catch (error) {
      lastError = error;
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

  alert(
    "Captured " +
      title +
      "\nLessons/sections found: " +
      metadata.lessonRecords +
      "\nDownloaded: " +
      stem +
      "_course.json"
  );
})().catch((error) => {
  alert("SCORM capture failed: " + error.message);
  console.error(error);
});
