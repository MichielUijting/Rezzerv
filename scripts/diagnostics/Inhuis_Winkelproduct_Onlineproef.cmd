@echo off
CLS
setlocal
set "INHUIS_DIAG_SELF=%~f0"
powershell.exe -NoProfile -Command "$raw=[IO.File]::ReadAllText($env:INHUIS_DIAG_SELF,[Text.Encoding]::GetEncoding(1252)); $mark=[char]35+'POWERSHELL_DIAGNOSTIC_BEGIN'; $separator=[Environment]::NewLine+$mark+[Environment]::NewLine; $idx=$raw.LastIndexOf($separator,[StringComparison]::Ordinal); if($idx -lt 0){ Write-Host 'FOUT: Diagnosedeel ontbreekt'; exit 2 }; $code=$raw.Substring($idx+$separator.Length); & ([ScriptBlock]::Create($code))"
set "RC=%ERRORLEVEL%"
CLS
if "%RC%"=="0" (
  echo INHUIS WINKELPRODUCT-ONLINEPROEF VOLTOOID.
  echo Het rapport staat in Downloads: Inhuis_Winkelproduct_Onlineproef_Resultaat.txt
) else (
  echo INHUIS WINKELPRODUCT-ONLINEPROEF VEILIG GESTOPT.
  echo Het rapport heet Inhuis_Winkelproduct_Onlineproef_Resultaat.txt.
  echo Als dat ontbreekt, stuur dan de foutmelding BOVEN dit scherm door.
)
echo.
echo Niets verwijderd, gestart, gestopt of gemigreerd.
pause
exit /b %RC%
#POWERSHELL_DIAGNOSTIC_BEGIN
$ErrorActionPreference = 'Stop'
$report = Join-Path (Join-Path $env:USERPROFILE 'Downloads') 'Inhuis_Winkelproduct_Onlineproef_Resultaat.txt'
if (-not (Test-Path -LiteralPath (Split-Path -Parent $report))) { $report = Join-Path $env:TEMP 'Inhuis_Winkelproduct_Onlineproef_Resultaat.txt' }
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('INHUIS WINKELPRODUCT-ONLINEPROEF - ALLEEN LEZEN')
$lines.Add(('Datum: {0:yyyy-MM-dd HH:mm:ss zzz}' -f [DateTimeOffset]::Now))
$lines.Add('Wijzigingen aan database, Docker en Git: GEEN')
$lines.Add('Anonieme online zoekopdrachten bij AH, Lidl en Jumbo; maximaal twee artikelen per winkel. Geen klantaccounts.')
# Rapporteer ook wanneer de controles vroegtijdig fail-closed stoppen.
$lines | Set-Content -LiteralPath $report -Encoding UTF8
function Note([string] $message) { $lines.Add($message) }
function SaveReport { $lines | Set-Content -LiteralPath $report -Encoding UTF8 }
try {
  $repo = Join-Path $env:USERPROFILE 'Rezzerv_CODEX_WORK'
  $scriptRoot = Split-Path -Parent $env:INHUIS_DIAG_SELF
  $candidate = Split-Path -Parent (Split-Path -Parent $scriptRoot)
  if (Test-Path -LiteralPath (Join-Path $candidate '.git')) { $repo = $candidate }
  if (Test-Path -LiteralPath (Join-Path (Get-Location).Path '.git')) { $repo = (Get-Location).Path }
  if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw 'Officiele Git-werkmap ontbreekt.' }
  if (-not (Test-Path -LiteralPath (Join-Path $repo 'docker-compose.yml'))) { throw 'Officiele Compose-configuratie ontbreekt.' }
  if (-not (Test-Path -LiteralPath (Join-Path $repo 'docker-compose.postgresql.yml'))) { throw 'PostgreSQL Compose-configuratie ontbreekt.' }
  if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw 'Docker CLI niet gevonden.' }
  if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { throw 'Git CLI niet gevonden.' }
  $branch = (& git.exe -C $repo branch --show-current 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Git-branch niet uitleesbaar.' }
  $head = (& git.exe -C $repo rev-parse HEAD 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Git-status kon niet worden gelezen.' }
  Note ('Lokale Git-branch: ' + $branch)
  Note ('Lokale Git-SHA: ' + $head)
  $envPath = Join-Path $repo '.env'
  if (-not (Test-Path -LiteralPath $envPath)) { throw 'Officiele .env ontbreekt; runtime niet geraden.' }
  Push-Location $repo
  try {
    $composeArgs = @('compose','--env-file','.env','-f','docker-compose.yml','-f','docker-compose.postgresql.yml','--profile','postgresql')
    $backendIds = @(& docker.exe @composeArgs ps -q backend 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Bestaande backend via officiele Compose-route niet uitleesbaar.' }
    $backendIds = @($backendIds | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
    if ($backendIds.Count -ne 1) { throw ('Niet precies een bestaande backend gevonden via deze Compose-route (aantal: ' + $backendIds.Count + '). Geen database gekozen.') }
    $backendId = $backendIds[0]
    Note ('Compose-backend-ID: ' + $backendId.Substring(0,12))
    # Inspect Docker JSON rather than passing Go-template quotes through Windows PowerShell.
    $backendInspectRaw = & docker.exe inspect $backendId 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker-backend inspectie mislukt.' }
    $backendInspect = @($backendInspectRaw | Out-String | ConvertFrom-Json)
    if ($backendInspect.Count -ne 1) { throw 'Docker-backend inspectie niet eenduidig.' }
    $backendState = [string]$backendInspect[0].State.Status
    $backendProject = [string]$backendInspect[0].Config.Labels.'com.docker.compose.project'
    Note ('Backend status en Compose-project: ' + $backendState + ' / ' + $backendProject)
    if ($backendState -ne 'running') { throw 'De bestaande backend draait niet; diagnose start niets.' }
    if ([string]$backendInspect[0].Config.Labels.'com.docker.compose.service' -ne 'backend') { throw 'Onverwachte backendservice.' }
    if ([string]::IsNullOrWhiteSpace($backendProject)) { throw 'Backend mist Compose-projectidentiteit; gestopt.' }
    $postgresIds = @(& docker.exe @composeArgs ps -q postgres 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL status via Compose-route niet uitleesbaar.' }
    $postgresIds = @($postgresIds | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
    Note ('PostgreSQL containers via dezelfde Compose-route: ' + $postgresIds.Count)
    if ($postgresIds.Count -ne 1) { throw 'Database-identiteit is niet eenduidig binnen deze Compose-route; gestopt.' }
    $postgresInspectRaw = & docker.exe inspect $postgresIds[0] 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker-PostgreSQL-inspectie mislukt.' }
    $postgresInspect = @($postgresInspectRaw | Out-String | ConvertFrom-Json)
    if ($postgresInspect.Count -ne 1) { throw 'Docker-PostgreSQL-inspectie niet eenduidig.' }
    $postgresProject = [string]$postgresInspect[0].Config.Labels.'com.docker.compose.project'
    if ([string]$postgresInspect[0].Config.Labels.'com.docker.compose.service' -ne 'postgres') { throw 'Onverwachte databaseservice.' }
    if ($postgresProject -ne $backendProject) { throw 'Backend en database hebben verschillende Compose-projecten; niets uitgelezen.' }
    # Python runs in the ALREADY RUNNING backend. No application imports, migrations or writes.
    function Invoke-ProbePython([string] $Code) {
      # Redirect through .NET: Windows PowerShell must not turn the first stderr
      # line into a terminating NativeCommandError and discard the traceback.
      $startInfo = [Diagnostics.ProcessStartInfo]::new()
      $startInfo.FileName = (Get-Command docker.exe -ErrorAction Stop).Source
      $arguments = 'exec -i -e PYTHONIOENCODING=utf-8 '
      $startInfo.Arguments = $arguments + $backendId + ' python -B -'
      $startInfo.UseShellExecute = $false
      $startInfo.CreateNoWindow = $true
      $startInfo.RedirectStandardInput = $true
      $startInfo.RedirectStandardOutput = $true
      $startInfo.RedirectStandardError = $true
      $startInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
      $startInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
      $process = [Diagnostics.Process]::new()
      $process.StartInfo = $startInfo
      try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($Code)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(180000)) {
          try { $process.Kill() } catch {}
          throw 'Bronproef duurde langer dan drie minuten; veilig gestopt.'
        }
        return [pscustomobject]@{ ExitCode=$process.ExitCode; Stdout=$stdoutTask.GetAwaiter().GetResult(); Stderr=$stderrTask.GetAwaiter().GetResult() }
      } finally { $process.Dispose() }
    }
    $pythonCode = @'
"""Bounded guest catalog proof using saved receipt identifiers, never writes.

Protocol references (independently implemented, no package code copied):
gwillem/appie-go: products.go, auth.go, ProductTradeItem GraphQL schema.
jgalea/grocery-cli: internal/lidl/lidl.go (/q/api/search).
vghoost360/Jumbo-API: public product search links and product(sku) query.
No customer accounts, cookie reuse, third-party proxy, or paid API.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from html.parser import HTMLParser
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


HOSTS = {"ah": "api.ah.nl", "lidl": "www.lidl.nl", "jumbo": "www.jumbo.com"}
AGENT = "Mozilla/5.0 (compatible; InhuisCatalogProbe/1.0)"
AH_HEADERS = {"User-Agent": "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)",
              "x-client-name": "appie-ios", "x-client-version": "9.28", "x-application": "AHWEBSHOP"}
MAX_BYTES = 8 * 1024 * 1024


class CatalogError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_url(provider, value):
    if provider not in HOSTS or not isinstance(value, str):
        raise CatalogError("invalid_url")
    url = urllib.parse.urljoin("https://" + HOSTS[provider] + "/", value)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOSTS[provider] or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
        raise CatalogError("invalid_url")
    return url


class GuestTransport:
    def __init__(self):
        self.calls = 0
        self.deadline = time.monotonic() + 120
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, provider, path, payload=None, token="", html=False):
        if self.calls >= 24 or time.monotonic() >= self.deadline:
            raise CatalogError("request_budget_exhausted")
        url = safe_url(provider, path)
        # Only two POSTs are permitted: a guest AH token and read-only product
        # GraphQL queries. No account login/cart/order/personal-data operations.
        if payload is not None:
            allowed = provider == "ah" and path == "/mobile-auth/v1/auth/token/anonymous"
            allowed |= provider in {"ah", "jumbo"} and path in {"/graphql", "/api/graphql"} and str(payload.get("query", "")).startswith("query InhuisCatalogProduct")
            if not allowed:
                raise CatalogError("operation_not_allowed")
        if token and provider != "ah":
            raise CatalogError("credential_host_mismatch")
        headers = {"User-Agent": AGENT, "Accept": "*/*" if provider == "lidl" or html else "application/json"}
        if provider == "ah":
            headers.update(AH_HEADERS)
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        self.calls += 1
        try:
            with self.opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=min(8, max(0.1, self.deadline-time.monotonic()))) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise CatalogError("response_too_large")
            return raw.decode("utf-8") if html else json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise CatalogError("http_" + str(exc.code)) from None
        except (OSError, ValueError, UnicodeError) as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError("transport_or_response_error") from None


def identifier(value):
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10**30:
        return str(value)
    return value.strip() if isinstance(value, str) and len(value) <= 180 else ""


def gtin(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value) or set(value) == {"0"}:
        return ""
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(value[:-1])))
    return value if (10-total % 10) % 10 == int(value[-1]) else ""


def tokens(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = re.sub(r"\bjong\s+belegen\b", "jongbelegen", value)
    return {t for t in re.findall(r"[a-z0-9]+", value) if len(t) >= 3 and t not in {"jumbo", "lidl", "albert", "heijn", "stuk", "stuks"}}


def name_compatible(source, candidate):
    wanted, actual = tokens(source), tokens(candidate)
    if not wanted or not actual or len(wanted & actual) / len(wanted) < 0.6:
        return False
    # Explicit variants cannot be undone by a high general name similarity.
    for family in ({"halfvolle", "volle", "magere"}, {"jonge", "oude", "belegen", "jongbelegen"}, {"houdbare", "verse"}):
        a, b = wanted & family, actual & family
        if a and a != b:
            return False
    return True


class ProductHtml(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.blocks, self.parts, self.capture = [], [], [], False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and isinstance(attrs.get("href"), str):
            self.links.append(attrs["href"])
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.capture, self.parts = True, []
    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            self.capture = False
            try: self.blocks.append(json.loads("".join(self.parts)))
            except ValueError: pass


def jsonld_products(html):
    parser = ProductHtml()
    parser.feed(html)
    found = []
    def walk(value, depth=0):
        if depth > 8:
            return
        if isinstance(value, list):
            for entry in value[:100]: walk(entry, depth+1)
        elif isinstance(value, dict):
            types = value.get("@type")
            if types == "Product" or isinstance(types, list) and "Product" in types:
                found.append(value)
            # Never borrow GTINs from offers, recommendations or sibling products.
            if "@graph" in value: walk(value["@graph"], depth+1)
    for block in parser.blocks: walk(block)
    return found


def outcome(source, candidates, rejected=0):
    valid = []
    for candidate in candidates:
        if not name_compatible(source["name"], candidate.get("name")):
            rejected += 1
            continue
        candidate = dict(candidate)
        candidate["gtin"] = gtin(candidate.get("gtin"))
        candidate["receipt_code_match"] = bool(source.get("sku")) and source["sku"] in candidate.get("receipt_codes", [])
        # An AH private-label receipt cannot become a different brand just
        # because an unrelated numeric namespace happened to match.
        if source["provider"] == "ah" and re.match(r"^AH\b", source["name"], re.I):
            brand = str(candidate.get("brand") or "").lower()
            if brand not in {"ah", "albert heijn"} and not re.match(r"^AH\b", candidate["name"], re.I):
                rejected += 1
                continue
        valid.append(candidate)
    exact = {c["gtin"].zfill(14) for c in valid if c["receipt_code_match"] and c["gtin"]}
    status = ("conflicting_barcode_evidence" if len(exact) > 1 else "receipt_code_and_catalog_gtin_observed" if exact
              else "receipt_code_match_no_gtin" if any(c["receipt_code_match"] for c in valid)
              else "name_suggestions_only" if valid else "no_compatible_product")
    # Identifiers/product data remain local to this call, not in the exported report.
    return {"status": status, "candidates": len(valid), "rejected": rejected,
            "catalog_products_with_gtin": sum(bool(c["gtin"]) for c in valid), "writes": 0}


class CatalogProbe:
    def __init__(self, transport):
        self.transport, self.ah_token = transport, ""

    def ah(self, source):
        if not self.ah_token:
            response = self.transport("ah", "/mobile-auth/v1/auth/token/anonymous", {"clientId": "appie-ios"})
            token = response.get("access_token") if isinstance(response, dict) else None
            if not isinstance(token, str) or not token or len(token) > 10000:
                raise CatalogError("guest_auth_response_invalid")
            self.ah_token = token
        cards = {}
        # Searching an hqId is only discovery. Match the hqId field explicitly;
        # NEVER use the receipt ID as a webshop product ID.
        queries = list(dict.fromkeys(q for q in (source.get("sku"), source["name"]) if q))
        for query in queries:
            payload = self.transport("ah", "/mobile-services/product/search/v2?" + urllib.parse.urlencode({"query": query, "size": 10, "page": 0, "sortOn": "RELEVANCE"}), token=self.ah_token)
            products = payload.get("products") if isinstance(payload, dict) else None
            if not isinstance(products, list): raise CatalogError("catalog_layout_unknown")
            for card in products[:10]:
                if isinstance(card, dict) and name_compatible(source["name"], card.get("title")):
                    webshop = identifier(card.get("webshopId"))
                    if webshop.isascii() and webshop.isdigit(): cards[webshop] = card
            if any(identifier(c.get("hqId")) == source.get("sku") for c in cards.values()): break
        ranked = sorted(cards.items(), key=lambda x: identifier(x[1].get("hqId")) == source.get("sku"), reverse=True)
        candidates = []
        for webshop, card in ranked[:2]:
            payload = self.transport("ah", "/graphql", {"query": "query InhuisCatalogProduct($id:Int!){product(id:$id){id title tradeItem{gtin}}}", "variables": {"id": int(webshop)}}, token=self.ah_token)
            product = payload.get("data", {}).get("product") if isinstance(payload, dict) else None
            if payload.get("errors") or not isinstance(product, dict) or identifier(product.get("id")) != webshop:
                raise CatalogError("product_identity_response_invalid")
            candidates.append({"name": product.get("title"), "brand": card.get("brand"),
                "receipt_codes": [identifier(card.get("hqId"))], "gtin": (product.get("tradeItem") or {}).get("gtin")})
        return outcome(source, candidates)

    def lidl(self, source):
        candidates, rejected = [], 0
        for query in list(dict.fromkeys(q for q in (source.get("sku"), source["name"]) if q)):
            payload = self.transport("lidl", "/q/api/search?" + urllib.parse.urlencode({"q": query, "assortment": "NL", "locale": "nl_NL", "version": "2.0"}))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list): raise CatalogError("catalog_layout_unknown")
            for item in items[:50]:
                data = item.get("gridbox", {}).get("data", {}) if isinstance(item, dict) else {}
                if not isinstance(data, dict) or not name_compatible(source["name"], data.get("fullTitle")):
                    rejected += 1
                    continue
                # ERP/webshop IDs and IANs are separate namespaces. Only an
                # explicit exact IAN observation is compared to a receipt code.
                codes = [identifier(v) for v in data.get("ians", [])] if isinstance(data.get("ians"), list) else []
                candidate = {"name": data["fullTitle"], "receipt_codes": codes, "gtin": ""}
                url = data.get("canonicalUrl")
                if url and len(candidates) < 2:
                    page = self.transport("lidl", safe_url("lidl", url), html=True)
                    products = [p for p in jsonld_products(page) if name_compatible(data["fullTitle"], p.get("name"))]
                    # Only a uniquely identified product object, never any EAN
                    # appearing somewhere on the page.
                    if len(products) == 1:
                        product = products[0]
                        candidate["gtin"] = next((gtin(product.get(k)) for k in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin") if gtin(product.get(k))), "")
                candidates.append(candidate)
                if len(candidates) >= 2: break
            if candidates: break
        return outcome(source, candidates, rejected)

    def jumbo(self, source):
        page = self.transport("jumbo", "/producten/?" + urllib.parse.urlencode({"searchType": "keyword", "searchTerms": source["name"]}), html=True)
        parser = ProductHtml()
        parser.feed(page)
        links = {}
        for link in parser.links:
            match = re.fullmatch(r"/producten/[a-zA-Z0-9_-]+-([0-9]{3,}[A-Z]{2,})", link)
            if match: links.setdefault(match[1], link)
        candidates = []
        for sku, link in list(links.items())[:2]:
            try:
                payload = self.transport("jumbo", "/api/graphql", {"query": "query InhuisCatalogProduct($sku:String!){product(sku:$sku){sku title brand ean}}", "variables": {"sku": sku}})
            except CatalogError as exc:
                if str(exc) not in {"http_401", "http_403"}: raise
                # The website can publish product metadata even when its API
                # requires an account. No login/session/cookie workaround.
                page = self.transport("jumbo", link, html=True)
                products = jsonld_products(page)
                matching = [p for p in products if identifier(p.get("sku")) == sku]
                if len(matching) != 1:
                    raise CatalogError("public_product_identity_unavailable") from None
                product = matching[0]
                candidates.append({"name": product.get("name"), "receipt_codes": [sku],
                    "gtin": next((gtin(product.get(k)) for k in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin") if gtin(product.get(k))), "")})
                continue
            product = payload.get("data", {}).get("product") if isinstance(payload, dict) else None
            if payload.get("errors") or not isinstance(product, dict) or product.get("sku") != sku:
                raise CatalogError("product_identity_response_invalid")
            candidates.append({"name": product.get("title"), "brand": product.get("brand"), "receipt_codes": [sku], "gtin": product.get("ean")})
        return outcome(source, candidates)

    def search(self, source):
        provider = source.get("provider")
        if provider not in HOSTS: return {"status": "provider_not_enabled", "writes": 0}
        try:
            return getattr(self, provider)(source)
        except CatalogError as exc:
            return {"status": "source_unavailable", "reason": str(exc), "writes": 0}
        except (ValueError, TypeError, KeyError, AttributeError):
            return {"status": "source_unavailable", "reason": "catalog_layout_unknown", "writes": 0}


def load_samples(conn):
    from sqlalchemy import text
    if conn.dialect.name != "postgresql" or conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise CatalogError("readonly_postgresql_required")
    rows = conn.execute(text("""
        WITH unique_articles AS (
          SELECT DISTINCT rs.source_path AS provider,
                 COALESCE(NULLIF(rtl.normalized_label,''),rtl.raw_label) AS name,
                 COALESCE(rtl.external_article_code,'') AS sku
          FROM receipt_table_lines rtl
          JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
          JOIN raw_receipts rr ON rr.id=rt.raw_receipt_id AND rr.household_id=rt.household_id
          JOIN receipt_sources rs ON rs.id=rr.source_id AND rs.household_id=rr.household_id
          WHERE rs.type='retailer_api' AND rs.source_path IN ('ah','lidl','jumbo')
            AND rtl.line_role='product' AND rtl.inventory_eligible=1
            AND COALESCE(rtl.is_deleted,FALSE)=FALSE
            AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL
            AND COALESCE(rt.workflow_state,'active') NOT IN ('removed','removed_reimport_allowed')
        ), numbered AS (
          SELECT *, row_number() OVER (PARTITION BY provider ORDER BY CASE WHEN sku<>'' THEN 0 ELSE 1 END,name,sku) AS n
          FROM unique_articles WHERE name IS NOT NULL AND name<>''
        ) SELECT provider,name,sku FROM numbered WHERE n<=2 ORDER BY provider,n
    """)).mappings().all()
    return [{"provider": row["provider"], "name": str(row["name"])[:240], "sku": str(row["sku"])[:180]} for row in rows]


def run(samples, transport):
    probe, groups = CatalogProbe(transport), {}
    for source in samples:
        group = groups.setdefault(source["provider"], {"provider": source["provider"], "samples": 0, "statuses": Counter(), "errors": Counter(), "catalog_products_with_gtin": 0, "rejected": 0})
        group["samples"] += 1
        result = probe.search(source)
        group["statuses"][result["status"]] += 1
        if result.get("reason"): group["errors"][result["reason"]] += 1
        group["catalog_products_with_gtin"] += result.get("catalog_products_with_gtin", 0)
        group["rejected"] += result.get("rejected", 0)
    return {"probe_version": 1, "read_only": True, "writes": 0, "groups": list(groups.values()),
        "network_requests": getattr(transport, "calls", None),
        "scope": "At most two distinct active stored articles per AH/Lidl/Jumbo, guest catalogs only; no coverage estimate",
        "picnic": "not_tested_no_account", "aldi": "not_enabled_no_verified_connector"}


def main():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = make_url(os.environ.get("DATABASE_URL") or "")
    if url.get_backend_name() != "postgresql" or url.host != "postgres" or (url.port or 5432) != 5432:
        raise CatalogError("existing_compose_postgresql_required")
    if url.drivername == "postgresql": url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, connect_args={"connect_timeout": 8}, isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout='25s'")
            conn.exec_driver_sql("SET LOCAL lock_timeout='3s'")
            samples = load_samples(conn)
        # Release the database snapshot BEFORE any external request.
        print(json.dumps(run(samples, GuestTransport()), ensure_ascii=True))
    finally: engine.dispose()


if __name__ == "__main__":
    try: main()
    except Exception:
        print("VEILIG GESTOPT: catalogusproef niet voltooid; geen gegevens gewijzigd.")
        raise SystemExit(1) from None
'@
    Write-Host 'Maximaal twee artikelen per winkel online toetsen. Dit kan enkele minuten duren...'
    $output = Invoke-ProbePython -Code $pythonCode
    if ($output.ExitCode -ne 0) { throw 'Onlineproef niet voltooid. Geen gegevens gewijzigd; bronuitvoer wordt niet gedeeld.' }
    $result = $output.Stdout.Trim() | ConvertFrom-Json
    if ($result.probe_version -ne 1 -or $result.read_only -ne $true -or $result.writes -ne 0) { throw 'Onverwacht diagnoseantwoord.' }
    Note 'ONLINEPROEF VOLTOOID - geen gegevens opgeslagen of gekoppeld.'
    Note ('Uitgevoerde online verzoeken: ' + $result.network_requests)
    if (@($result.groups).Count -eq 0) { Note 'GEEN ACTIEVE DIGITALE PRODUCTREGELS GEVONDEN: geen winkelkoppeling getest.' }
    foreach ($group in $result.groups) {
      Note (('Winkel: {0}; onderzochte verschillende artikelen: {1}' -f $group.provider,$group.samples))
      Note ('Uitkomsten: ' + ($group.statuses | ConvertTo-Json -Compress))
      Note ('Bronfouten: ' + ($group.errors | ConvertTo-Json -Compress))
      Note (('Passende winkelproducten met geldige GTIN: {0}; afgewezen resultaten: {1}' -f $group.catalog_products_with_gtin,$group.rejected))
    }
    Note 'receipt_code_and_catalog_gtin_observed = dezelfde boncode in een benoemd catalogusveld plus een expliciete GTIN aangetroffen; nog geen opgeslagen koppeling.'
    Note 'receipt_code_match_no_gtin = overeenkomstige winkelcode, maar geen geldige barcode beschikbaar.'
    Note 'name_suggestions_only = passende naamsuggesties, zonder bewezen overeenkomstige boncode.'
    Note 'no_compatible_product = geen voldoende passend product in de onderzochte resultaten.'
    Note 'conflicting_barcode_evidence = tegenstrijdige barcodes; niets gekozen.'
    Note 'source_unavailable = bron weigerde of gaf een onbekend antwoord; dit is geen bewijs dat het product ontbreekt.'
    Note 'Deze beperkte steekproef zegt niets over de dekking van het gehele assortiment.'
    Note 'Picnic: niet getest zonder account. Aldi: nog geen geverifieerde connector geactiveerd.'
    Note 'VOLGENDE STAP: upload dit TXT-rapport in de chat. Geen bronbonnen, accounts of tokens meesturen.'
  } finally { Pop-Location }
} catch {
  Note ('VEILIG GESTOPT: ' + $_.Exception.Message)
  try { SaveReport } catch { Write-Host 'Rapport kon niet worden opgeslagen.' }
  Write-Host ('Rapport: ' + $report)
  exit 1
}
SaveReport
exit 0
