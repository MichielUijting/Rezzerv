$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8E-0 runtime regex hardening starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8

if ($content -match 'class _RezzervSafeRegexModule') {
    Write-Host 'Runtime regex hardening was al aanwezig.' -ForegroundColor Yellow
} else {
$insert = @'

# Rezzerv 8E-0 guardrail:
# OCR text can contain mojibake characters. Some legacy cleaning code builds
# regex character classes dynamically. When a dash lands between two runtime
# characters, Python can raise: re.error: bad character range X-Y.
# This local proxy only retries patterns that actually fail with that error.
# It does not change normal regex behavior.
_rezzerv_raw_re = re


def _rezzerv_escape_bad_character_ranges(pattern):
    if not isinstance(pattern, str):
        return pattern
    result = []
    in_class = False
    escaped = False
    class_started = False
    length = len(pattern)
    for index, char in enumerate(pattern):
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == '\\':
            result.append(char)
            escaped = True
            continue
        if char == '[' and not in_class:
            in_class = True
            class_started = True
            result.append(char)
            continue
        if char == ']' and in_class:
            in_class = False
            class_started = False
            result.append(char)
            continue
        if char == '-' and in_class:
            next_char = pattern[index + 1] if index + 1 < length else ''
            if not class_started and next_char not in {']', ''}:
                result.append('\\-')
            else:
                result.append(char)
            class_started = False
            continue
        result.append(char)
        if in_class and class_started and char != '^':
            class_started = False
    return ''.join(result)


def _rezzerv_retry_regex_call(callable_obj, pattern, *args, **kwargs):
    try:
        return callable_obj(pattern, *args, **kwargs)
    except _rezzerv_raw_re.error as exc:
        message = str(exc)
        if 'bad character range' not in message:
            raise
        safe_pattern = _rezzerv_escape_bad_character_ranges(pattern)
        if safe_pattern == pattern:
            raise
        return callable_obj(safe_pattern, *args, **kwargs)


class _RezzervSafeRegexModule:
    def __init__(self, raw_module):
        self._raw = raw_module

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def compile(self, pattern, flags=0):
        return _rezzerv_retry_regex_call(self._raw.compile, pattern, flags)

    def sub(self, pattern, repl, string, count=0, flags=0):
        return _rezzerv_retry_regex_call(self._raw.sub, pattern, repl, string, count, flags)

    def subn(self, pattern, repl, string, count=0, flags=0):
        return _rezzerv_retry_regex_call(self._raw.subn, pattern, repl, string, count, flags)

    def match(self, pattern, string, flags=0):
        return _rezzerv_retry_regex_call(self._raw.match, pattern, string, flags)

    def fullmatch(self, pattern, string, flags=0):
        return _rezzerv_retry_regex_call(self._raw.fullmatch, pattern, string, flags)

    def search(self, pattern, string, flags=0):
        return _rezzerv_retry_regex_call(self._raw.search, pattern, string, flags)

    def findall(self, pattern, string, flags=0):
        return _rezzerv_retry_regex_call(self._raw.findall, pattern, string, flags)

    def finditer(self, pattern, string, flags=0):
        return _rezzerv_retry_regex_call(self._raw.finditer, pattern, string, flags)

    def split(self, pattern, string, maxsplit=0, flags=0):
        return _rezzerv_retry_regex_call(self._raw.split, pattern, string, maxsplit, flags)


re = _RezzervSafeRegexModule(_rezzerv_raw_re)
'@

    $marker = 'import re'
    if (-not $content.Contains($marker)) {
        throw 'Kan import re niet vinden in receipt_service.py'
    }
    $content = $content.Replace($marker, ($marker + $insert))
    Copy-Item $path "$path.runtime-regex-hardening-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Runtime regex hardening toegevoegd aan receipt_service.py' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna opnieuw POST /api/receipt-import-diagnosis/zip-dry-run testen met supermarkten.zip.' -ForegroundColor Yellow
