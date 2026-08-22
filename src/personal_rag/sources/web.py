"""Safe, deterministic fetching of one server-rendered HTML page.

The adapter deliberately has no JavaScript execution path. It validates the destination
before every request and redirect, checks robots.txt, limits the response, and emits only
visible article-like text as untrusted source data.
"""

import hashlib
import html
import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..models import DiscoveryRequest, RawDocument, SourceDescriptor, SourceItem
from .base import AdapterError

MAX_RESPONSE_BYTES = 5_000_000
MAX_REDIRECTS = 5
PARSER_VERSION = "html-main-content/1"
_HIDDEN_TAGS = {"script", "style", "noscript", "template", "svg", "canvas"}
_TEXT_TAGS = {"p", "li", "pre", "blockquote", "dd", "dt"}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_HEADING = re.compile(r"h([1-6])", re.IGNORECASE)


@dataclass
class ExtractedHTML:
    text: str
    title: str
    canonical_url: str | None = None
    published_at: str | None = None
    links: tuple[str, ...] = ()


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list["_Node | str"] = field(default_factory=list)


class _HTMLTree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {}, [])
        self.stack = [self.root]
        self.meta: dict[str, str] = {}
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = {str(key).lower(): str(value or "") for key, value in attrs}
        node = _Node(tag.lower(), normalized, [])
        self.stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self.stack.append(node)
        if tag.lower() == "meta":
            key = normalized.get("name") or normalized.get("property")
            value = normalized.get("content")
            if key and value:
                self.meta[key.lower()] = value.strip()
        if tag.lower() == "link" and normalized.get("rel", "").lower() == "canonical":
            self.meta["canonical"] = normalized.get("href", "")
        if tag.lower() == "a" and normalized.get("href"):
            self.links.append(normalized["href"])

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].children.append(data)


def _node_text(node: _Node) -> str:
    return " ".join(
        child if isinstance(child, str) else _node_text(child) for child in node.children
    ).strip()


def _find_nodes(node: _Node, tag: str) -> list[_Node]:
    found = [node] if node.tag == tag else []
    for child in node.children:
        if isinstance(child, _Node):
            found.extend(_find_nodes(child, tag))
    return found


def _render(node: _Node, lines: list[str]) -> None:
    if (
        node.tag in _HIDDEN_TAGS
        or "hidden" in node.attrs
        or node.attrs.get("aria-hidden") == "true"
    ):
        return
    text = _node_text(node)
    heading = _HEADING.fullmatch(node.tag)
    if heading and text:
        lines.append(f"{'#' * int(heading.group(1))} {text}")
        return
    if node.tag in _TEXT_TAGS and text:
        lines.append(text)
        return
    for child in node.children:
        if isinstance(child, _Node):
            _render(child, lines)


def extract_html(payload: str) -> ExtractedHTML:
    parser = _HTMLTree()
    parser.feed(payload)
    parser.close()
    candidates = _find_nodes(parser.root, "article") or _find_nodes(parser.root, "main")
    if not candidates:
        body = _find_nodes(parser.root, "body")
        candidates = body or [parser.root]
    lines: list[str] = []
    _render(candidates[0], lines)
    title_nodes = _find_nodes(parser.root, "title")
    title = _node_text(title_nodes[0]) if title_nodes else parser.meta.get("og:title", "")
    published = (
        parser.meta.get("article:published_time")
        or parser.meta.get("datepublished")
        or parser.meta.get("date")
    )
    return ExtractedHTML(
        text="\n\n".join(dict.fromkeys(line for line in lines if line)).strip(),
        title=html.unescape(title).strip() or "Untitled page",
        canonical_url=parser.meta.get("canonical"),
        published_at=published,
        links=tuple(parser.links),
    )


def normalize_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError("only HTTPS URLs are allowed")
    host = parts.hostname.lower().rstrip(".")
    port = parts.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit(("https", netloc, path, parts.query, ""))


def _allowed_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


class WebAdapter:
    source_type = "web"
    adapter_version = "web-http/1"
    parser_version = PARSER_VERSION

    def __init__(
        self,
        descriptor: SourceDescriptor,
        *,
        client_factory: Callable[..., httpx.Client] | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.descriptor = descriptor
        configuration = descriptor.configuration
        raw_url = configuration.get("url")
        if not raw_url:
            raise ValueError(f"source {descriptor.source_id!r} needs a 'url' configuration key")
        try:
            self.url = normalize_url(str(raw_url))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"source {descriptor.source_id!r} has an invalid HTTPS URL") from exc
        self.allow_hosts = {
            str(host).lower().rstrip(".") for host in configuration.get("allow_hosts", [])
        }
        if self.allow_hosts and urlsplit(self.url).hostname not in self.allow_hosts:
            raise ValueError("the configured URL is outside the host allowlist")
        self.max_bytes = int(configuration.get("max_bytes", MAX_RESPONSE_BYTES))
        self.timeout = float(configuration.get("timeout", 15.0))
        self.max_redirects = int(configuration.get("max_redirects", MAX_REDIRECTS))
        self.user_agent = str(configuration.get("user_agent", "personal-rag/1"))
        self.client_factory = client_factory or httpx.Client
        self.resolver = resolver or self._resolve_public_addresses

    def discover(self, request: DiscoveryRequest) -> Iterable[SourceItem]:
        if request.limit == 0:
            return
        revision = str(self.descriptor.configuration.get("revision", self.url))
        if request.changed_only and request.known_revisions.get(self.url) == revision:
            return
        yield SourceItem(
            item_id=self.url,
            source_id=self.descriptor.source_id,
            source_uri=self.url,
            media_type="text/html",
            title=self.descriptor.display_name,
            source_revision=revision,
        )

    def fetch(self, item: SourceItem) -> RawDocument:
        current = normalize_url(item.source_uri)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        try:
            with self.client_factory(
                follow_redirects=False, timeout=self.timeout, headers=headers
            ) as client:
                self._check_robots(client, current)
                response = None
                for _ in range(self.max_redirects + 1):
                    self._validate_destination(current)
                    response = client.get(current)
                    if response.status_code not in {301, 302, 303, 307, 308}:
                        break
                    location = response.headers.get("location")
                    if not location:
                        raise AdapterError("redirect has no Location header", item_id=item.item_id)
                    current = normalize_url(urljoin(current, location))
                    self._check_robots(client, current)
                else:
                    raise AdapterError("too many redirects", item_id=item.item_id)
        except AdapterError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise AdapterError(
                "web request failed", item_id=item.item_id, status="unreadable"
            ) from exc

        assert response is not None
        if response.status_code >= 400:
            raise AdapterError(
                f"web server returned HTTP {response.status_code}", item_id=item.item_id
            )
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
            raise AdapterError(
                f"unsupported content type {content_type}",
                item_id=item.item_id,
                status="unsupported",
            )
        body = response.content
        if len(body) > self.max_bytes:
            raise AdapterError(
                "web response exceeds the configured size limit", item_id=item.item_id
            )
        extracted = extract_html(body.decode(response.encoding or "utf-8", errors="replace"))
        if not extracted.text:
            raise AdapterError("web page has no extractable visible content", item_id=item.item_id)
        canonical = (
            normalize_url(urljoin(current, extracted.canonical_url))
            if extracted.canonical_url
            else current
        )
        published_at = _parse_datetime(extracted.published_at)
        revision = (
            response.headers.get("etag")
            or response.headers.get("last-modified")
            or hashlib.sha256(body).hexdigest()
        )
        return RawDocument(
            item=item,
            text=extracted.text,
            title=extracted.title,
            source_revision=revision,
            parser_version=self.parser_version,
            fetched_at=datetime.now(UTC),
            published_at=published_at,
            metadata={
                "source_url": item.source_uri,
                "canonical_url": canonical,
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "robots_allowed": True,
                "links": tuple(urljoin(current, link) for link in extracted.links if link),
            },
        )

    def fingerprint(self, document: RawDocument) -> str:
        return hashlib.sha256(document.text.encode("utf-8")).hexdigest()

    def _check_robots(self, client: httpx.Client, url: str) -> None:
        robots_url = urlunsplit(("https", urlsplit(url).netloc, "/robots.txt", "", ""))
        self._validate_destination(robots_url)
        response = client.get(robots_url)
        if response.status_code in {401, 403}:
            raise AdapterError(
                "robots.txt disallows fetching this host", item_id=url, status="quarantined"
            )
        if response.status_code >= 400:
            return
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(self.user_agent, url):
            raise AdapterError("robots.txt disallows this URL", item_id=url, status="quarantined")

    def _validate_destination(self, url: str) -> None:
        normalized = normalize_url(url)
        host = urlsplit(normalized).hostname or ""
        if self.allow_hosts and host not in self.allow_hosts:
            raise ValueError("redirect leaves the host allowlist")
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError("local host is not allowed")
        addresses = self.resolver(host)
        if not addresses or any(not _allowed_ip(address) for address in addresses):
            raise ValueError("destination resolves to a private or otherwise unsafe address")

    @staticmethod
    def _resolve_public_addresses(host: str) -> list[str]:
        return list(
            {result[4][0] for result in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None
