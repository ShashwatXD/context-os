"""Gmail via the official API (read-only OAuth scope)."""

from __future__ import annotations

import base64
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser

from contextos.config import Config
from contextos.models import Message

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_BODY_CHARS = 6000

# Gmail's own tabs. Promotions/Social get dropped later; Updates/Forums are kept as low priority.
AUTOMATED_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
NOREPLY = re.compile(r"(no-?reply|do-?not-?reply|notifications?|mailer-daemon|newsletter|digest)@", re.I)
QUOTE_START = re.compile(r"^(On .{5,200}wrote:|-{2,} ?Original Message ?-{2,}|From: .+)$", re.I)


class AuthRequired(RuntimeError):
    pass


class GmailSource:
    name = "gmail"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def is_configured(self) -> bool:
        return self.cfg.gmail_token.exists()

    def setup_hint(self) -> str:
        if not self.cfg.gmail_credentials.exists():
            return f"put your OAuth client file at {self.cfg.gmail_credentials}, then run `contextos auth gmail`"
        return "run `contextos auth gmail`"

    # ---- auth ---------------------------------------------------------------

    def authorize(self) -> str:
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.cfg.gmail_credentials.exists():
            raise AuthRequired(f"Missing {self.cfg.gmail_credentials}. See README → Gmail setup.")
        flow = InstalledAppFlow.from_client_secrets_file(str(self.cfg.gmail_credentials), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        self.cfg.gmail_token.write_text(creds.to_json())
        self.cfg.gmail_token.chmod(0o600)
        return self._service().users().getProfile(userId="me").execute()["emailAddress"]

    def _service(self):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(self.cfg.gmail_token), SCOPES)
        if not creds.valid:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                raise AuthRequired("Gmail login expired. Run `contextos auth gmail` again.") from e
            self.cfg.gmail_token.write_text(creds.to_json())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ---- fetch --------------------------------------------------------------

    def fetch(self, since: datetime) -> Iterator[Message]:
        svc = self._service()
        me = svc.users().getProfile(userId="me").execute()["emailAddress"]
        query = f"after:{int(since.timestamp())} -in:spam -in:trash"

        ids: list[str] = []
        page_token = None
        while len(ids) < self.cfg.gmail_max_messages:
            resp = svc.users().messages().list(userId="me", q=query, maxResults=100, pageToken=page_token).execute()
            ids += [m["id"] for m in resp.get("messages", [])]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        for raw in _get_many(svc, ids[: self.cfg.gmail_max_messages]):
            yield parse_message(raw, me)


def _get_many(svc, ids: list[str], batch_size: int = 25) -> Iterator[dict]:
    """Fetch full messages with batched HTTP requests (one round-trip per 25 messages)."""
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        results: dict[str, dict] = {}
        failed: list[str] = []

        def on_done(request_id, response, exception, results=results, failed=failed):
            if exception is None:
                results[request_id] = response
            else:
                failed.append(request_id)

        batch = svc.new_batch_http_request(callback=on_done)
        for mid in chunk:
            batch.add(svc.users().messages().get(userId="me", id=mid, format="full"), request_id=mid)
        batch.execute()
        # Batches can partially fail on rate limits; retry those one at a time
        # (the client library backs off and retries on 429/5xx when num_retries is set).
        for mid in failed:
            results[mid] = svc.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=3)
        yield from (results[mid] for mid in chunk if mid in results)


# ---- parsing (pure functions, unit-tested) -----------------------------------


def parse_message(raw: dict, me: str) -> Message:
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    labels = raw.get("labelIds", [])

    from_name, from_addr = parseaddr(headers.get("from", ""))
    recipients = [a.lower() for _, a in getaddresses([headers.get("to", ""), headers.get("cc", "")])]
    automated = (
        bool(AUTOMATED_LABELS.intersection(labels))
        or "list-unsubscribe" in headers
        or headers.get("precedence", "").lower() in {"bulk", "list", "junk"}
        or headers.get("auto-submitted", "no").lower() != "no"
        or bool(NOREPLY.search(from_addr))
    )
    is_from_me = "SENT" in labels or from_addr.lower() == me.lower()
    body = clean_body(extract_body(payload)) or raw.get("snippet", "")

    return Message(
        id=f"gmail:{raw['id']}",
        source="gmail",
        channel="Sent" if is_from_me else "Inbox",
        author="me" if is_from_me else (from_name or from_addr or "unknown"),
        ts=datetime.fromtimestamp(int(raw["internalDate"]) / 1000, UTC),
        text=body[:MAX_BODY_CHARS],
        title=headers.get("subject", "(no subject)"),
        thread_id=f"gmail:{raw.get('threadId', raw['id'])}",
        url=f"https://mail.google.com/mail/u/{me}/#all/{raw.get('threadId', raw['id'])}",
        is_to_me=(me.lower() in recipients) and not is_from_me and not automated,
        is_from_me=is_from_me,
        is_automated=automated,
        labels=labels,
    )


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    """Walk the MIME tree. Prefer text/plain; fall back to text/html converted to text."""
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            html.append(_decode(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain)
    return "\n".join(html_to_text(h) for h in html)


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "blockquote"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return "".join(p.out)


def clean_body(text: str) -> str:
    """Drop quoted replies and signatures-by-convention, collapse whitespace."""
    kept = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if QUOTE_START.match(stripped) and kept:
            break  # everything after "On <date>, X wrote:" is the previous email
        if stripped.startswith(">"):
            continue
        if stripped == "--":
            break
        kept.append(stripped)
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t ‌]{2,}", " ", text)
    return text.strip()
