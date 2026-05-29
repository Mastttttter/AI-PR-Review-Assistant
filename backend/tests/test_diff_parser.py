from apr_backend.services.diff_parser import (
    FileEntry,
    ParsedDiff,
    parse_diff,
    _looks_like_diff,
    _language_from_path,
    _is_test_path,
    _extract_sensitive_keywords,
)

MULTI_FILE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc123..def456 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,8 @@ def login(user, password):
     if not user:
         return None
+    if not user.is_active:
+        return None
     token = generate_token(user)
     return token
@@ -30,4 +32,2 @@ def logout(token):
     revoke_token(token)
-    log_action("logout")
-    return True

diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,5 @@
+def test_login_active_user():
+    user = User(is_active=True)
+    result = login(user, "secret")
+    assert result is not None
+
"""

RENAME_DIFF = """\
diff --git a/src/old_module.py b/src/new_module.py
rename from src/old_module.py
rename to src/new_module.py
--- a/src/old_module.py
+++ b/src/new_module.py
@@ -5,3 +5,3 @@ def helper():
-    return "old"
+    return "new"
"""

SINGLE_HUNK_DIFF = """\
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,4 @@
 def foo():
-    pass
+    x = 1
+    return x
"""

PLAIN_SNIPPET = """\
def refresh_token(user):
    token = generate_new_token(user.secret)
    return token
"""


class TestParseDiff:
    def test_empty_diff_returns_empty_result(self) -> None:
        result = parse_diff("")
        assert result.files == []
        assert result.metrics.file_count == 0

    def test_whitespace_only_diff_returns_empty_result(self) -> None:
        result = parse_diff("   \n  \n  ")
        assert result.files == []
        assert result.metrics.file_count == 0

    def test_multi_file_diff_parses_all_files(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        assert result.metrics.file_count == 2
        assert not result.is_plain_snippet
        paths = [f.path for f in result.files]
        assert "src/auth.py" in paths
        assert "tests/test_auth.py" in paths

    def test_multi_file_diff_metrics(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        assert result.metrics.added_lines > 0
        assert result.metrics.deleted_lines > 0
        assert result.metrics.contains_test_file is True
        assert "auth" in result.metrics.sensitive_keywords

    def test_rename_diff_preserves_old_path(self) -> None:
        result = parse_diff(RENAME_DIFF)
        assert result.metrics.file_count == 1
        entry = result.files[0]
        assert entry.path == "src/new_module.py"
        assert entry.old_path == "src/old_module.py"

    def test_single_hunk_line_counts(self) -> None:
        result = parse_diff(SINGLE_HUNK_DIFF)
        entry = result.files[0]
        assert entry.added_lines == 2
        assert entry.deleted_lines == 1

    def test_new_file_mode(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        test_file = next(f for f in result.files if f.path == "tests/test_auth.py")
        assert test_file.is_new is True

    def test_plain_snippet_fallback(self) -> None:
        result = parse_diff(PLAIN_SNIPPET)
        assert result.is_plain_snippet is True
        assert result.metrics.file_count == 1
        assert result.files[0].path == "snippet"


class TestHelpers:
    def test_looks_like_diff_detects_git_header(self) -> None:
        assert _looks_like_diff("diff --git a/x b/x\n")
        assert not _looks_like_diff("def foo():\n    pass\n")

    def test_language_from_path(self) -> None:
        assert _language_from_path("src/main.py") == "python"
        assert _language_from_path("app.tsx") == "typescript"
        assert _language_from_path("lib/util.js") == "javascript"
        assert _language_from_path("Dockerfile") == "dockerfile"
        assert _language_from_path("unknown.xyz") is None

    def test_is_test_path(self) -> None:
        assert _is_test_path("tests/test_auth.py") is True
        assert _is_test_path("src/__tests__/auth.test.ts") is True
        assert _is_test_path("src/auth.spec.ts") is True
        assert _is_test_path("spec/auth_test.rb") is True
        assert _is_test_path("src/auth.py") is False

    def test_sensitive_keywords(self) -> None:
        kw = _extract_sensitive_keywords("use password and token to auth")
        assert "auth" in kw
        assert "password" in kw
        assert "token" in kw
        assert "secret" not in kw


class TestLanguageAndTestDetection:
    def test_language_hints_on_multi_file_diff(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        langs = result.metrics.languages
        assert "python" in langs

    def test_test_file_detected_in_metrics(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        assert result.metrics.contains_test_file is True

    def test_no_test_file_in_metrics(self) -> None:
        result = parse_diff(SINGLE_HUNK_DIFF)
        assert result.metrics.contains_test_file is False
