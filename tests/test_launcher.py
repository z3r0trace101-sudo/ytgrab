"""Static checks on scripts/run.ps1.

There is no PowerShell interpreter in the normal test environment (Linux CI,
this project's sandbox), so these tests cannot execute the script or catch
every syntax error. They check the things that matter most without running
it: that it does not silently violate the project's "no system install, no
PATH/registry changes, no admin rights, HTTPS + verified downloads" rules,
and a few structural sanity checks (balanced braces/parens, no leftover
placeholder bugs). Real execution must still be verified by hand on Windows,
see the project's CONTRIBUTING notes / release checklist.
"""

from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "run.ps1"
)


def _read_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_launcher_script_exists() -> None:
    assert SCRIPT_PATH.is_file()


def test_launcher_never_requests_admin_elevation() -> None:
    text = _read_script().lower()
    forbidden = ("runas", "requireadministrator", "start-process -verb runas")
    for marker in forbidden:
        assert marker not in text, f"launcher must not elevate ({marker!r} found)"


def test_launcher_does_not_modify_path_or_registry() -> None:
    text = _read_script()
    # Match the command itself, not the word appearing inside a comment
    # explaining that the script deliberately avoids it.
    assert "setx " not in text.lower() and "setx\t" not in text.lower()
    assert "New-ItemProperty" not in text
    assert "Set-ItemProperty" not in text
    assert "HKCU:" not in text and "HKLM:" not in text
    assert "[Environment]::SetEnvironmentVariable" not in text


def test_launcher_only_downloads_over_https() -> None:
    text = _read_script()
    # Every literal URL in the script must use https://. This does not catch
    # a URL built dynamically from an insecure scheme, so it's paired with
    # test_download_helper_rejects_non_https_urls below.
    import re

    urls = re.findall(r"https?://\S+", text)
    assert urls, "expected at least one URL in the launcher"
    for url in urls:
        assert url.startswith("https://"), f"non-HTTPS URL found: {url}"


def test_download_helper_rejects_non_https_urls() -> None:
    text = _read_script()
    assert "Invoke-HttpsDownload" in text
    assert 'notlike "https://*"' in text
    assert "Refusing to download from a non-HTTPS URL" in text


def test_launcher_verifies_uv_checksum_before_use() -> None:
    text = _read_script()
    assert "Get-FileHash" in text
    assert "Assert-FileSha256" in text
    assert "sha256" in text.lower()


def test_launcher_downloads_only_come_from_expected_hosts() -> None:
    import re

    text = _read_script()
    urls = re.findall(r"https://[^\s\"']+", text)
    allowed_hosts = (
        "github.com",
        "raw.githubusercontent.com",
    )
    # "https://*" is the wildcard literal used by the HTTPS-only guard clause,
    # not an actual download target.
    urls = [u for u in urls if u != "https://*"]
    for url in urls:
        assert any(url.startswith(f"https://{h}") for h in allowed_hosts), (
            f"unexpected host in launcher URL: {url}"
        )


def test_launcher_does_not_use_the_github_releases_api() -> None:
    # The launcher must work against a plain `main` branch with no GitHub
    # Release ever having been created, and must never call the GitHub API
    # (which is also unauthenticated-rate-limited, unlike a plain archive
    # download). This is a regression test for a real bug: an earlier
    # version resolved "latest" through /releases/latest and failed with
    # "Not Found" on a repository that had no releases yet.
    text = _read_script()
    assert "/releases/latest" not in text
    assert "api.github.com" not in text
    assert "Invoke-RestMethod" not in text


def test_launcher_default_version_uses_main_branch_archive() -> None:
    text = _read_script()
    assert (
        '"https://github.com/$RepoOwner/$RepoName/archive/refs/heads/main.zip"'
        in text
    )


def test_launcher_specific_version_uses_tag_archive() -> None:
    text = _read_script()
    assert (
        '"https://github.com/$RepoOwner/$RepoName/archive/refs/tags/'
        "$RequestedVersion.zip\"" in text
    )


def test_launcher_repo_owner_and_name_are_correct() -> None:
    text = _read_script()
    assert '$RepoOwner = "z3r0trace101-sudo"' in text
    assert '$RepoName = "ytgrab"' in text


def test_resolve_archive_url_checks_latest_before_falling_back_to_tag() -> None:
    # A structural check of Resolve-YtgrabArchiveUrl's body: the "latest"
    # comparison must appear, followed by the main-branch URL, followed by
    # the tag URL as the fallback — i.e. "latest" is handled specially and
    # anything else is treated as a tag, not the other way around.
    text = _read_script()
    start = text.index("function Resolve-YtgrabArchiveUrl")
    end = text.index("\n}", start)
    body = text[start:end]
    latest_check_pos = body.index('$RequestedVersion -eq "latest"')
    main_url_pos = body.index("archive/refs/heads/main.zip")
    tag_url_pos = body.index("archive/refs/tags/")
    assert latest_check_pos < main_url_pos < tag_url_pos


def test_launcher_restricts_writes_to_user_profile_folders() -> None:
    text = _read_script()
    assert "$env:LOCALAPPDATA" in text
    assert "$env:TEMP" in text
    # A hardcoded "C:\Program Files" style system path would be a red flag.
    assert "Program Files" not in text
    assert "$env:windir" not in text and "$env:SystemRoot" not in text


def test_launcher_cleans_up_its_temporary_work_directory() -> None:
    text = _read_script()
    assert "WorkDir" in text
    assert "Remove-Item $paths.WorkDir" in text


def test_launcher_sets_ffmpeg_path_without_touching_system_path() -> None:
    text = _read_script()
    assert "YTGRAB_FFMPEG" in text
    assert '$env:Path' not in text and "$env:PATH" not in text


def test_launcher_has_balanced_braces_and_parens() -> None:
    text = _read_script()
    pairs = {"{": "}", "(": ")", "[": "]"}
    closers = set(pairs.values())
    stack: list[str] = []
    in_string = False
    quote = ""
    i = 0
    while i < len(text):
        char = text[i]
        if in_string:
            if char == quote:
                in_string = False
            i += 1
            continue
        if char in ("'", '"'):
            in_string, quote = True, char
            i += 1
            continue
        if char == "#":
            newline = text.find("\n", i)
            i = newline if newline != -1 else len(text)
            continue
        if text[i : i + 2] == "<#":
            end = text.find("#>", i)
            assert end != -1, "unterminated <# ... #> block comment"
            i = end + 2
            continue
        if char in pairs:
            stack.append(char)
        elif char in closers:
            assert stack, f"unmatched closing {char!r} at offset {i}"
            opener = stack.pop()
            assert pairs[opener] == char, (
                f"mismatched {opener!r}/{char!r} at offset {i}"
            )
        i += 1
    assert not stack, f"unclosed opening bracket(s): {stack}"


def test_launcher_has_no_leftover_placeholder_type_names() -> None:
    # Regression check for a bug caught during development: a parameter typed
    # as a made-up class (e.g. "[Paths]$Paths") fails at parse time in real
    # PowerShell, but nothing in this Linux-only test suite would otherwise
    # notice, since it never actually parses the script as PowerShell.
    text = _read_script()
    assert "[Paths]" not in text


def test_readme_documents_the_exact_launcher_command() -> None:
    readme = (
        Path(__file__).resolve().parent.parent / "README.md"
    ).read_text(encoding="utf-8")
    assert "scripts/run.ps1" in readme
    assert "irm " in readme and " | iex" in readme
