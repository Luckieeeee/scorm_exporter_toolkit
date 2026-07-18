# SCORM Exporter Toolkit

This folder points to the reusable D2L/SCORM export workflow in this workspace.
It lets you capture a D2L unit yourself and export it to searchable Markdown,
HTML, and PDF without asking Codex to scrape it each time.

## 1. Capture from D2L

1. Open the D2L unit in your logged-in browser.
2. Wait until the SCORM/Rise content is visible.
3. Run this script in that D2L tab by pasting it into DevTools Console:

   `/Users/baka/Documents/Codex/2026-07-14/i-wa/work/scorm_tools/capture_bookmarklet.js`

For repeated use, create a browser bookmark named `Capture D2L SCORM` and set
its URL to the contents of:

`/Users/baka/Documents/Codex/2026-07-14/i-wa/outputs/scorm_exporter_toolkit/capture_bookmarklet_url.txt`

The script downloads:

- `<tid>_<course_title>_course.json`
- `<tid>_<course_title>_capture_metadata.json`

Nothing is uploaded. The script only reads the current browser page and creates
local downloads.

## 2. Export to Searchable Files

Run:

```bash
/Users/baka/Documents/Codex/2026-07-14/i-wa/outputs/scorm_exporter_toolkit/export_scorm.sh \
  ~/Downloads/<tid>_<course_title>_course.json \
  "My_Course_Unit" \
  styled
```

The exporter writes these files to `/Users/baka/Documents/Codex/2026-07-14/i-wa/outputs`:

- `My_Course_Unit.md`
- `My_Course_Unit.html`
- `My_Course_Unit.pdf`
- `My_Course_Unit_extraction_report.json`

Use `plain` instead of `styled` for a simpler export.

## 3. Current Implementation Files

- Capture helper:
  `/Users/baka/Documents/Codex/2026-07-14/i-wa/work/scorm_tools/capture_bookmarklet.js`
- Export wrapper:
  `/Users/baka/Documents/Codex/2026-07-14/i-wa/outputs/scorm_exporter_toolkit/export_scorm.sh`
- Python formatter:
  `/Users/baka/Documents/Codex/2026-07-14/i-wa/work/export_scorm_course.py`
