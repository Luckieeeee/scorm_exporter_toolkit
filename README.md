# SCORM Exporter Toolkit

A small self-serve toolkit for exporting D2L / Articulate Rise SCORM course
content to searchable Markdown, HTML, and PDF.

The workflow has two parts:

- Capture `course.json` from a D2L page where you are already logged in.
- Convert that JSON locally into printable/searchable files.

Nothing is uploaded by the capture script. It reads the current browser page and
downloads local files.

## Requirements

- Python 3.10+
- `reportlab`

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## 1. Capture From D2L

### Recommended: Tampermonkey

Open the D2L unit in your browser and wait until the SCORM/Rise content is
visible.

1. Install the Tampermonkey browser extension.
2. Create a new userscript.
3. Replace its contents with `d2l_scorm_capture.user.js`.
4. Save the userscript.
5. Open a D2L unit. A `Capture SCORM` button appears in the bottom-right corner.
6. Click `Capture SCORM`.

If the button is hidden by D2L's frame layout, click the Tampermonkey extension
icon and choose `Capture current D2L SCORM` from the script menu.

The capture downloads:

- `<tid>_<course_title>_course.json`
- `<tid>_<course_title>_capture_metadata.json`

The Tampermonkey script runs only on the top D2L viewer page. This prevents the
same capture from firing in D2L's nested frames and creating duplicate
`unknown_tid` downloads.

### Alternative: Bookmarklet

For one-time use, paste the contents of `capture_bookmarklet.js` into DevTools
Console on the D2L tab and press Enter.

For repeated use:

1. Create a browser bookmark named `Capture D2L SCORM`.
2. Set the bookmark URL to the contents of `capture_bookmarklet_url.txt`.
3. Open a D2L unit, wait for the SCORM content to load, then click the bookmark.

## 2. Export Searchable Files

### Recommended: Watch Downloads

Start the watcher before capturing from D2L:

```bash
./watch_downloads.sh
```

Then click `Capture SCORM` in D2L. When Tampermonkey downloads a new
`*_course.json` file, the watcher automatically exports Markdown, HTML, PDF,
and the extraction report to `./outputs`.

By default, the watcher ignores matching files that were already in Downloads
when it started. To export existing captures too, run:

```bash
./watch_downloads.sh --process-existing
```

To scan once and exit:

```bash
./watch_downloads.sh --once
```

The watcher uses styled export by default. Use plain mode with:

```bash
./watch_downloads.sh --mode plain
```

Use a different downloads folder or export folder with:

```bash
./watch_downloads.sh --watch-dir ~/Desktop --output-dir ./exports
```

### Manual Export

From this repository folder, run:

```bash
./export_scorm.sh ~/Downloads/<tid>_<course_title>_course.json "My_Course_Unit" styled
```

This writes files to `./outputs`:

- `My_Course_Unit.md`
- `My_Course_Unit.html`
- `My_Course_Unit.pdf`
- `My_Course_Unit_extraction_report.json`

Use `plain` instead of `styled` for a simpler document:

```bash
./export_scorm.sh ~/Downloads/<tid>_<course_title>_course.json "My_Course_Unit" plain
```

You can also choose a custom output folder:

```bash
./export_scorm.sh ~/Downloads/<tid>_<course_title>_course.json "My_Course_Unit" styled ./exports
```

## Notes

- Styled mode preserves more of the Rise structure: accent color, bold/emphasis,
  numbered/check/bullet blocks, callouts, tabs, accordions, and question blocks.
- The PDF is generated as selectable/searchable text, not screenshots.
- If capture fails, scroll the SCORM page until the content is fully loaded and
  run the bookmarklet again.
- The exporter intentionally omits answer-key correctness flags and hidden
  feedback fields.

## Troubleshooting Tampermonkey

If the `Capture SCORM` button does not appear:

1. Open the D2L page and click the Tampermonkey extension icon.
2. Confirm `D2L SCORM Capture` appears under the current site and is enabled.
3. Confirm userscripts are enabled in Tampermonkey.
4. Try the Tampermonkey menu command: `Capture current D2L SCORM`.
5. In Chrome, check that Tampermonkey is allowed to run on `d2l.ucalgary.ca`.
