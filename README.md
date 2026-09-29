# ytgrab

ytgrab is a small Windows 10/11 desktop application for downloading YouTube
videos and audio that **you own or have permission to download**, through a
simple graphical interface.

Repository: <https://github.com/z3r0trace101-sudo/ytgrab> (branch `main`).

---

## For end users (no Python, no installs)

Open **Windows PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/z3r0trace101-sudo/ytgrab/main/scripts/run.ps1 | iex
```

That's the whole process. What happens next, automatically:

1. The script fetches a small, isolated copy of Python and yt-dlp — not a
   system-wide Python install. It never touches any Python you may already
   have, never runs `pip install` globally, and never edits PATH or the
   Windows registry.
2. It fetches a portable FFmpeg build for merging video/audio — again, not
   installed system-wide, and not added to PATH.
3. The ytgrab window opens.
4. You paste a YouTube link, pick video or audio, pick a quality, and click
   Download.
5. When you close the window, the script cleans up this run's temporary
   files. See **What gets left behind** below for exactly what does and
   doesn't get removed.

**You do not need to**, and should not be asked to: install Python, install
pip, create a virtual environment, run `pip install`, install FFmpeg, add
anything to PATH, install Git, or clone this repository. If a step asks you
to do any of that, something is wrong — please open an issue.

### System requirements

- Windows 10 or Windows 11
- PowerShell 5.1 or newer (already included in Windows 10/11)
- Internet access (only during download steps; not needed once ytgrab is
  running, except to actually fetch the YouTube video)
- No Administrator rights needed

### What gets left behind

| Location | What's there | Removed when? |
|---|---|---|
| `%LOCALAPPDATA%\ytgrab\runtime\` | The downloaded uv tool, the managed Python it fetched, and the portable FFmpeg build | Kept after each run so the *next* launch is fast, since these are the same files every time. Delete manually, or run with `-FullCleanup`, to remove them completely. |
| `%TEMP%\ytgrab-run-<id>\` | This run's copy of the ytgrab source and its Python environment | Deleted automatically as soon as you close ytgrab |
| `%LOCALAPPDATA%\ytgrab\logs\` | Application log files (for troubleshooting) | Kept; see Troubleshooting below |
| Your chosen download folder | The videos/audio you downloaded | Never touched by cleanup, obviously |

There is nothing to "uninstall" in the traditional sense: there is no
installer, nothing is registered with Windows, and nothing is added to
PATH. Deleting `%LOCALAPPDATA%\ytgrab` removes everything ytgrab has ever
written to your system.

To force a fully clean run that also wipes the reusable cache afterward:

```powershell
irm https://raw.githubusercontent.com/z3r0trace101-sudo/ytgrab/main/scripts/run.ps1 -OutFile run.ps1
.\run.ps1 -FullCleanup
```

(A piped `irm | iex` can't take parameters, so pinning a version or
requesting full cleanup means saving the script first, as above.)

### How this works, technically

`scripts/run.ps1` uses [uv](https://github.com/astral-sh/uv), an
open-source Python package/environment manager, to fetch an isolated Python
interpreter and ytgrab's one dependency (`yt-dlp`) without installing
anything system-wide. It separately downloads a portable, statically-linked
FFmpeg build and points ytgrab at it directly through an environment
variable (`YTGRAB_FFMPEG`), scoped to that one process — never PATH, never
the registry. This is the same "PowerShell → single command → the tool just
runs" experience popularized by tools like Chris Titus Tech's WinUtil;
ytgrab's launcher is its own, independent script, not a copy of theirs.

### Security

Running `irm <url> | iex` downloads a script and executes it immediately,
which is exactly why this README shows you the script's contents are worth
reading before you run it — `scripts/run.ps1` is plain text, and you're
encouraged to open it in a browser or editor first. To make that review
easy and meaningful:

- Every download in the script uses `https://` and is checked before use;
  the script refuses to download from a plain `http://` URL.
- Every download comes from a hardcoded GitHub domain
  (`github.com` or `raw.githubusercontent.com`) — there is no logic that
  builds a URL from user input or from anything the script downloads, and
  the script never calls the GitHub API.
- The `uv` tool download is verified against its official published SHA256
  checksum before it is extracted or run; a mismatch aborts immediately and
  deletes the file.
- By default (`-Version latest`), the ytgrab source is fetched from the
  current `main` branch archive. This does **not** require a GitHub Release
  to exist, but it also means the archive can change between runs — it is
  not pinned or checksummed. Pass a specific tag once one exists, e.g.
  `-Version "v1.0.0"`, to fetch that exact, immutable tagged archive instead
  (a git tag can't be silently changed without it being visible on GitHub).
- The FFmpeg build (from the widely used
  [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) project) is
  the one exception: that project does not publish a per-release checksum
  file, so this download is checked only for being a well-formed zip
  archive, not against a known hash. If you'd rather supply your own
  trusted FFmpeg build, set `YTGRAB_FFMPEG` to its path yourself before
  running the script and remove/skip the FFmpeg download step.
- The script never requests Administrator rights, never writes to the
  registry, never modifies PATH, and only writes inside your own
  `%LOCALAPPDATA%` and `%TEMP%` folders.

If you'd rather not use `irm | iex` at all, download `scripts/run.ps1`,
read it, and run it locally — that's equally supported and arguably safer,
since you're reviewing exact bytes before execution rather than trusting
the pipe.

### Troubleshooting

- **"Running scripts is disabled on this system"**: PowerShell's execution
  policy blocked the script. `irm | iex` runs in-memory and is usually
  unaffected, but if you saved the script to a file first, run:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry.
- **The window doesn't open, or an error appears**: check
  `%LOCALAPPDATA%\ytgrab\logs\ytgrab.log` for details. Error messages shown
  in the app itself are deliberately non-technical; the log has the rest.
- **"Couldn't connect to YouTube"**: check your internet connection.
  YouTube also occasionally blocks or rate-limits automated access; trying
  again after a short wait often helps.
- **A download keeps failing on one specific video**: the video may be
  private, age-restricted, region-locked, or otherwise inaccessible to you,
  in which case ytgrab is behaving correctly by refusing it — see
  *Legal / responsible use* below.
- **Something in `scripts/run.ps1` itself seems to fail**: please open an
  issue with the console output. yt-dlp changes fairly often as YouTube
  changes; if metadata fetching abruptly breaks for everyone, the most
  common cause is that yt-dlp needs an update, which happens automatically
  the next time `uv` resolves dependencies from PyPI (there is no pinned
  upper version), unless a `uv.lock`/cache is stale — see `-FullCleanup`.

---

## For developers

Requires Python 3.11 or newer.

```powershell
git clone https://github.com/z3r0trace101-sudo/ytgrab.git
cd ytgrab
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m ytgrab
pytest
ruff check .
```

If activation fails with an execution-policy error, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

FFmpeg is required to actually download (metadata fetching alone does not
need it). For development, either install FFmpeg normally and make sure
it's on PATH, or set the `YTGRAB_FFMPEG` environment variable to point at
any `ffmpeg.exe` — the same variable `scripts/run.ps1` uses for end users.

### Project layout

```
ytgrab/
├── scripts/
│   └── run.ps1              end-user launcher (ephemeral runtime, see above)
├── src/ytgrab/
│   ├── app.py                Tkinter startup
│   ├── ui/main_window.py     the GUI (threaded, never blocks on downloads)
│   ├── core/
│   │   ├── url_validation.py  pure URL parsing/validation, no I/O
│   │   ├── downloader.py      the ONLY module that imports yt_dlp
│   │   ├── media_info.py      URL -> yt-dlp -> our own MediaInfo model
│   │   ├── models.py          shared dataclasses (no yt-dlp/Tkinter types)
│   │   ├── errors.py          user-facing error types
│   │   └── ffmpeg.py          finds a usable ffmpeg (bundled, then PATH)
│   └── support/
│       ├── paths.py           Downloads folder, app-data folder
│       └── logging_setup.py   rotating log file + console
├── tests/                     unit tests; no network access required
└── .github/workflows/         lint + test CI (see below)
```

Architecture rule: `core` never imports from `ui`, and only
`core/downloader.py` imports `yt_dlp`. Everything else works with ytgrab's
own dataclasses and exception types, so the yt-dlp dependency can change
without rippling through the codebase, and the GUI can eventually be
replaced without touching the download logic.

### Running tests

```powershell
pytest
ruff check .
```

The whole suite runs offline: yt-dlp and network calls are mocked/stubbed,
so nothing here contacts YouTube. `tests/test_launcher.py` does what static
checking of `scripts/run.ps1` is possible without a PowerShell interpreter
(no system installs, HTTPS-only, no PATH/registry edits, checksum
verification present, balanced syntax). It is not a substitute for actually
running the script on Windows before a release — see the release checklist
in `.github/workflows/`.

### Continuous integration

`.github/workflows/ci.yml` runs `ruff check .` and `pytest` on every push
and pull request, on both Windows and Linux runners (Linux mainly to keep
the core/URL/model logic honest about being platform-independent; the GUI
and FFmpeg paths are Windows-specific and are exercised by hand before a
release). There is no build/packaging workflow: ytgrab is distributed as
source, fetched at run time by `scripts/run.ps1`, so there is no separate
executable to build or sign for this to work.

### Cutting a release

No GitHub Release is required for the launcher to work: `-Version latest`
(the default) always fetches the current `main` branch archive, so pushing
to `main` is all that's needed to publish an update. If you want users to be
able to pin an exact, immutable version (`.\run.ps1 -Version "v1.0.0"`),
push a git tag with that name — no GitHub Release object needs to be
created for the tag archive to be downloadable. There is currently no
automated tagging/release workflow; add one only if pinned versions become
something this project actually needs.

## Legal / responsible use

ytgrab is intended only for downloading content that you own or have
permission to download. It does not attempt to bypass DRM, paywalls,
logins, or any other access restriction, and it will not download videos
that YouTube itself does not make available to you (private, region-locked,
members-only, etc.) — see the error messages in `core/errors.py`.

## License

MIT. See [LICENSE](LICENSE).
