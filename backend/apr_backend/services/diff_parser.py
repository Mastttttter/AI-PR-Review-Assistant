from __future__ import annotations

import re
from dataclasses import dataclass, field

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".md": "markdown",
    ".tf": "terraform",
    ".dockerfile": "dockerfile",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".vue": "vue",
    ".svelte": "svelte",
}

TEST_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(^|/)test(s?)[/_]"),
    re.compile(r"(^|/)__tests__[/]"),
    re.compile(r"(^|/)spec[/]"),
    re.compile(r"[._-]test\.([^.]+)$"),
    re.compile(r"[._-]spec\.([^.]+)$"),
    re.compile(r"\.test\.([^.]+)$"),
    re.compile(r"\.spec\.([^.]+)$"),
    re.compile(r"(^|/)tests?\.py$"),
]

SENSITIVE_KEYWORDS: list[str] = [
    "auth",
    "token",
    "password",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "jwt",
    "oauth",
    "certificate",
    "encrypt",
    "decrypt",
    "hash",
    "permission",
    "role",
    "admin",
    "csrf",
    "xss",
    "sql_inject",
    "sqlinject",
    "sanitize",
    "authorize",
    "authenticate",
    "session",
    "cookie",
    "pii",
    "gdpr",
]

DIFF_HEADER_RE = re.compile(r"^diff --git ", re.MULTILINE)
FILE_HEADER_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)
NEW_FILE_RE = re.compile(r"^new file mode", re.MULTILINE)
DELETED_FILE_RE = re.compile(r"^deleted file mode", re.MULTILINE)
RENAME_FROM_RE = re.compile(r"^rename from (.*?)$", re.MULTILINE)
RENAME_TO_RE = re.compile(r"^rename to (.*?)$", re.MULTILINE)
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$", re.MULTILINE)
ADDED_LINE_RE = re.compile(r"^\+")
DELETED_LINE_RE = re.compile(r"^-")


def _language_from_path(path: str) -> str | None:
    for ext, lang in LANGUAGE_MAP.items():
        if path.endswith(ext):
            return lang
    basename = path.rsplit("/", 1)[-1]
    if basename.lower() == "dockerfile":
        return "dockerfile"
    if basename.lower() == "makefile":
        return "makefile"
    return None


def _is_test_path(path: str) -> bool:
    return any(pattern.search(path) for pattern in TEST_PATH_PATTERNS)


def _extract_sensitive_keywords(text: str) -> list[str]:
    text_lower = text.lower()
    found: set[str] = set()
    for keyword in SENSITIVE_KEYWORDS:
        if keyword in text_lower:
            found.add(keyword)
    return sorted(found)


@dataclass
class Hunk:
    old_start: int
    new_start: int
    old_count: int
    new_count: int
    header: str
    content: str

    def __post_init__(self) -> None:
        lines = self.content.split("\n")
        if self.content.endswith("\n"):
            lines = lines[:-1]
        self.added_lines = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        self.deleted_lines = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))


@dataclass
class FileEntry:
    path: str
    language: str | None
    added_lines: int
    deleted_lines: int
    hunks: list[Hunk]
    is_test: bool = False
    is_new: bool = False
    is_deleted: bool = False
    old_path: str | None = None


@dataclass
class DiffMetrics:
    file_count: int
    added_lines: int
    deleted_lines: int
    contains_test_file: bool
    sensitive_keywords: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)


@dataclass
class ParsedDiff:
    files: list[FileEntry]
    metrics: DiffMetrics
    is_plain_snippet: bool = False


def parse_diff(content: str) -> ParsedDiff:
    if not content or not content.strip():
        return _empty_result()

    if not _looks_like_diff(content):
        return _parse_as_snippet(content)

    files: list[FileEntry] = []
    raw_files = _split_diff_files(content)

    for raw in raw_files:
        entry = _parse_one_file(raw)
        if entry is not None:
            files.append(entry)

    if not files:
        return _parse_as_snippet(content)

    return _build_result(files, is_snippet=False)


def _looks_like_diff(content: str) -> bool:
    return bool(DIFF_HEADER_RE.search(content))


def _split_diff_files(content: str) -> list[str]:
    matches = list(DIFF_HEADER_RE.finditer(content))
    blocks: list[str] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        blocks.append(content[start:end])
    return blocks


def _parse_one_file(raw: str) -> FileEntry | None:
    header_match = FILE_HEADER_RE.search(raw)
    if not header_match:
        return None

    path_b = header_match.group(2).strip()
    path_a = header_match.group(1).strip()
    path = path_b if path_b else path_a

    is_new = bool(NEW_FILE_RE.search(raw))
    is_deleted = bool(DELETED_FILE_RE.search(raw))
    old_path: str | None = None

    rename_from = RENAME_FROM_RE.search(raw)
    rename_to = RENAME_TO_RE.search(raw)
    if rename_from and rename_to:
        old_path = rename_from.group(1).strip()
        path = rename_to.group(1).strip()
    elif path_a != path_b and path_a != "/dev/null":
        old_path = path_a

    hunks = _parse_hunks(raw)
    added = sum(h.added_lines for h in hunks)
    deleted = sum(h.deleted_lines for h in hunks)

    return FileEntry(
        path=path,
        language=_language_from_path(path),
        added_lines=added,
        deleted_lines=deleted,
        hunks=hunks,
        is_test=_is_test_path(path),
        is_new=is_new,
        is_deleted=is_deleted,
        old_path=old_path,
    )


def _parse_hunks(raw: str) -> list[Hunk]:
    hunks: list[Hunk] = []
    matches = list(HUNK_HEADER_RE.finditer(raw))

    for i, match in enumerate(matches):
        old_start = int(match.group(1))
        old_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)
        header = match.group(0)

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end]

        hunks.append(Hunk(
            old_start=old_start,
            new_start=new_start,
            old_count=old_count,
            new_count=new_count,
            header=header,
            content=body,
        ))

    return hunks


def _parse_as_snippet(content: str) -> ParsedDiff:
    file_entry = FileEntry(
        path="snippet",
        language=None,
        added_lines=content.count("\n") + 1,
        deleted_lines=0,
        hunks=[],
    )

    return _build_result([file_entry], is_snippet=True)


def _build_result(files: list[FileEntry], is_snippet: bool) -> ParsedDiff:
    all_text = " ".join(f.path for f in files)
    sensitive = _extract_sensitive_keywords(all_text)
    languages = sorted({f.language for f in files if f.language})

    return ParsedDiff(
        files=files,
        metrics=DiffMetrics(
            file_count=len(files),
            added_lines=sum(f.added_lines for f in files),
            deleted_lines=sum(f.deleted_lines for f in files),
            contains_test_file=any(f.is_test for f in files),
            sensitive_keywords=sensitive,
            languages=languages,
        ),
        is_plain_snippet=is_snippet,
    )


def _empty_result() -> ParsedDiff:
    return ParsedDiff(
        files=[],
        metrics=DiffMetrics(
            file_count=0,
            added_lines=0,
            deleted_lines=0,
            contains_test_file=False,
        ),
        is_plain_snippet=False,
    )
