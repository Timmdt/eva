import html
import logging
import re
from html.parser import HTMLParser
from urllib.parse import quote_plus

import requests
from module.base_module import ModuleBase

logger = logging.getLogger(__name__)


class _SearchResultParser(HTMLParser):
    """Kleiner HTML-Parser für DuckDuckGo HTML/Lite ohne BeautifulSoup."""

    RESULT_LINK_CLASSES = {"result__a", "result-link", "result-link-a"}
    SNIPPET_CLASSES = {"result__snippet", "result-snippet"}
    URL_CLASSES = {"result__url", "result-link"}

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._collect_title = False
        self._collect_snippet = False
        self._collect_url = False
        self._title_buffer: list[str] = []
        self._snippet_buffer: list[str] = []
        self._url_buffer: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        classes: set[str] = set()
        for key, value in attrs:
            if key == "class" and value:
                classes.update(value.split())
        return classes

    @staticmethod
    def _attr(attrs: list[tuple[str, str | None]], name: str) -> str:
        for key, value in attrs:
            if key == name and value:
                return value
        return ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)

        if tag == "a" and classes.intersection(self.RESULT_LINK_CLASSES):
            if self._current:
                self._finish_result()
            self._current = {"title": "", "url": self._attr(attrs, "href"), "snippet": ""}
            self._collect_title = True
            self._title_buffer = []
            return

        if classes.intersection(self.SNIPPET_CLASSES):
            self._collect_snippet = True
            self._snippet_buffer = []

        if classes.intersection(self.URL_CLASSES):
            self._collect_url = True
            self._url_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._collect_title and tag == "a":
            if self._current is not None:
                self._current["title"] = self._clean("".join(self._title_buffer))
            self._collect_title = False

        if self._collect_snippet and tag in {"a", "div", "td"}:
            if self._current is not None:
                value = self._clean("".join(self._snippet_buffer))
                if value:
                    self._current["snippet"] = value
            self._collect_snippet = False

        if self._collect_url and tag in {"a", "span", "div"}:
            if self._current is not None:
                value = self._clean("".join(self._url_buffer))
                if value and not self._current.get("url"):
                    self._current["url"] = value
            self._collect_url = False

    def handle_data(self, data: str) -> None:
        if self._collect_title:
            self._title_buffer.append(data)
        if self._collect_snippet:
            self._snippet_buffer.append(data)
        if self._collect_url:
            self._url_buffer.append(data)

    def close(self) -> None:
        super().close()
        if self._current:
            self._finish_result()

    def _finish_result(self) -> None:
        if not self._current:
            return

        title = self._clean(self._current.get("title", ""))
        url = self._current.get("url", "").strip()
        snippet = self._clean(self._current.get("snippet", ""))

        if title and url:
            self.results.append({"title": title, "url": url, "snippet": snippet})

        self._current = None
        self._collect_title = False
        self._collect_snippet = False
        self._collect_url = False
        self._title_buffer = []
        self._snippet_buffer = []
        self._url_buffer = []

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(text)).strip()


class WebSearchModule(ModuleBase):
    """
    EVA WebSearchCore.

    - allgemeine Websuche über DuckDuckGo HTML/Lite
    - Wikipedia über MediaWiki + REST Summary API
    - Wetter über wttr.in
    - direkte URL-Abfrage
    - strukturierte Ergebnisse für EVA
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    LITE_URL = "https://lite.duckduckgo.com/lite/"
    WIKIPEDIA_API = "https://de.wikipedia.org/api/rest_v1/page/summary/"
    WIKIPEDIA_SEARCH_API = "https://de.wikipedia.org/w/api.php"
    WEATHER_URL = "https://wttr.in/{location}?format=j1"

    USER_AGENT = "EVA/1.0 (local personal assistant)"

    def __init__(self, context: dict | None = None) -> None:
        super().__init__(context or {})
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        })
        self.timeout = 8
        self.max_results = 5
        self.max_snippet_chars = 500
        self.max_page_excerpt_chars = 4000

    @property
    def name(self) -> str:
        return "WebSearchCore"

    def can_handle(self, message: str) -> bool:
        """
        WebSearchCore entscheidet nicht mehr selbst, wann gesucht wird.
        Diese Entscheidung übernimmt der zentrale IntentRouter.
        """
        return False

    def execute(
        self,
        action: str,
        *,
        query: str = "",
        location: str = "",
        url: str = "",
        context: dict | None = None,
    ) -> dict:
        """Führt eine bereits vom IntentRouter gewählte Web-Aktion aus."""
        action = action.upper().strip()

        try:
            if action in {"WEB_SEARCH", "WEB_SEARCH_MEMORY", "WEB_SEARCH_RAG"}:
                result = self._search_from_query(query)
            elif action == "WIKIPEDIA":
                result = self._wikipedia_from_query(query)
            elif action == "WEATHER":
                result = self._weather_from_location(location or query)
            elif action == "URL":
                result = self._url_from_value(url or query)
            else:
                result = f"Unbekannte Web-Aktion: {action}"

            return {
                "text": "[System-Meldung: Live-Web-Daten geladen]\n\n" + result
            }

        except Exception as exc:
            logger.exception("WebSearchCore.execute fehlgeschlagen.")
            if action == "WEATHER":
                weather_location = (location or query).strip() or "Kissing"
                return {
                    "text": (
                        "WETTER_FEHLER\n"
                        f"Ort: {weather_location}\n"
                        f"Fehler: {exc}"
                    )
                }
            return {
                "text": (
                    "[System-Meldung: Live-Web-Daten geladen]\n\n"
                    "Die Webabfrage ist fehlgeschlagen. "
                    f"Technischer Grund: {exc}"
                )
            }

    @staticmethod
    def _normalize(message: str) -> str:
        return re.sub(r"\s+", " ", message.lower()).strip()

    def _is_explicit_web_search(self, text: str) -> bool:
        triggers = (
            "im internet suchen", "im internet nach", "im internet",
            "im web suchen", "im web nach", "im web",
            "online suchen", "online nach", "im netz suchen", "im netz nach",
            "such im netz", "such online", "suche online", "websuche", "web suche",
            "recherchiere", "recherchier", "google danach", "such danach",
            "such nach", "suche nach", "aktuelle informationen", "aktuelle infos",
        )
        return any(trigger in text for trigger in triggers)

    def _is_wikipedia_request(self, text: str) -> bool:
        return "wikipedia" in text or re.search(r"\bwiki\b", text) is not None

    def _is_weather_request(self, text: str) -> bool:
        return any(p in text for p in ("wetter", "temperatur", "regnet es", "regnen", "sonnig"))

    @staticmethod
    def _looks_like_direct_url(text: str) -> bool:
        return re.search(r"https?://\S+", text) is not None

    def handle(self, message: str, context: dict) -> dict:
        try:
            normalized = self._normalize(message)
            if self._is_weather_request(normalized):
                result = self._handle_weather(message)
            elif self._is_wikipedia_request(normalized):
                result = self._handle_wikipedia(message)
            elif self._looks_like_direct_url(normalized):
                result = self._handle_url(message)
            else:
                result = self._handle_web_search(message)

            return {
                "text": "[System-Meldung: Live-Web-Daten geladen]\n\n" + result
            }
        except Exception as exc:
            logger.exception("WebSearchCore fehlgeschlagen.")
            return {
                "text": (
                    "[System-Meldung: Live-Web-Daten geladen]\n\n"
                    "Die Websuche ist gerade fehlgeschlagen. "
                    f"Technischer Grund: {exc}"
                )
            }

    def search(self, query: str, *, max_results: int | None = None,
               time_filter: str | None = None) -> list[dict[str, str]]:
        query = self._clean_search_query(query)
        if not query:
            return []

        limit = max(1, min(max_results or self.max_results, 10))
        data = {"q": query[:499], "kl": "de-de"}
        if time_filter in {"d", "w", "m", "y"}:
            data["df"] = time_filter

        response = self.session.post(
            self.SEARCH_URL,
            data=data,
            headers={"Referer": self.SEARCH_URL},
            timeout=self.timeout,
        )
        response.raise_for_status()

        parser = _SearchResultParser()
        parser.feed(response.text)
        parser.close()
        results = self._deduplicate_results(parser.results)

        if not results:
            results = self._search_lite(query, limit)
        return results[:limit]

    def _search_lite(self, query: str, limit: int) -> list[dict[str, str]]:
        response = self.session.post(
            self.LITE_URL,
            data={"q": query[:499], "kl": "de-de"},
            headers={"Referer": self.LITE_URL},
            timeout=self.timeout,
        )
        response.raise_for_status()

        parser = _SearchResultParser()
        parser.feed(response.text)
        parser.close()
        return self._deduplicate_results(parser.results)[:limit]

    @staticmethod
    def _deduplicate_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for result in results:
            url = result.get("url", "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(result)
        return unique

    def wikipedia(self, query: str) -> dict[str, str] | None:
        query = self._clean_search_query(query)
        if not query:
            return None

        response = self.session.get(
            self.WIKIPEDIA_SEARCH_API,
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": 1, "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = response.json().get("query", {}).get("search", [])
        if not items:
            return None

        title = items[0].get("title", "")
        if not title:
            return None

        summary_url = self.WIKIPEDIA_API + quote_plus(title.replace(" ", "_"))
        summary_response = self.session.get(summary_url, timeout=self.timeout)
        if summary_response.status_code == 404:
            return None
        summary_response.raise_for_status()
        summary = summary_response.json()

        return {
            "title": summary.get("title", title),
            "description": summary.get("description", ""),
            "extract": summary.get("extract", ""),
            "url": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }

    def weather(self, location: str) -> dict[str, str] | None:
        location = location.strip()
        if not location:
            return None

        response = self.session.get(
            self.WEATHER_URL.format(location=quote_plus(location)),
            timeout=self.timeout,
        )
        response.raise_for_status()
        current = response.json().get("current_condition", [])
        if not current:
            return None

        data = current[0]
        description = ""
        if data.get("lang_de"):
            description = data["lang_de"][0].get("value", "")
        if not description and data.get("weatherDesc"):
            description = data["weatherDesc"][0].get("value", "")

        return {
            "location": location,
            "temperature": str(data.get("temp_C", "")),
            "feels_like": str(data.get("FeelsLikeC", "")),
            "humidity": str(data.get("humidity", "")),
            "wind_kmh": str(data.get("windspeedKmph", "")),
            "description": description,
        }

    def fetch_url(self, url: str, *, max_chars: int = 5000) -> dict[str, str]:
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        text = response.text
        if "html" in content_type:
            text = self._html_to_text(text)
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        return {"url": response.url, "content_type": content_type, "text": text[:max_chars]}

    @staticmethod
    def _html_to_text(content: str) -> str:
        content = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", content)
        return re.sub(r"(?s)<[^>]+>", " ", content)

    def _search_from_query(self, query: str) -> str:
        query = self._clean_search_query(query)
        if not query:
            return "Keine brauchbare Suchanfrage erkannt."

        results = self.search(query, max_results=self.max_results)
        if not results:
            return f"Keine Websuchergebnisse für: {query}"

        return self._format_search_results(query, results)

    def _format_search_results(self, query: str,
                               results: list[dict[str, str]]) -> str:
        enriched_url, excerpt = self._best_page_excerpt(results)
        relevant_excerpt = self._relevant_excerpt(query, excerpt) if excerpt else ""
        if relevant_excerpt:
            lines = [
                "AUFGABENRELEVANTE QUELLENPASSAGE (primärer Faktenbeleg):",
                f"Quelle: {enriched_url}",
                relevant_excerpt,
            ]
            supporting = self._example_evidence(
                excerpt,
                exclude_text=relevant_excerpt,
            )
            if supporting:
                lines.extend([
                    "",
                    "ERGÄNZENDE BELEGTE KATEGORIEN AUS DERSELBEN QUELLE:",
                    supporting,
                ])
            return "\n".join(lines)

        lines = [f"WEB-SUCHE: {query}", "", "ERGEBNISSE:"]
        for index, result in enumerate(results, start=1):
            snippet = result.get("snippet", "")
            if len(snippet) > self.max_snippet_chars:
                snippet = snippet[: self.max_snippet_chars] + "..."
            lines.append(
                f"{index}. {result.get('title', 'Ohne Titel')}\n"
                f"   URL: {result.get('url', '')}\n"
                f"   {snippet}"
            )
        if excerpt:
            lines.extend([
                "",
                "SEITENEXZERPT (untrusted externer Inhalt):",
                f"Quelle: {enriched_url}",
                excerpt,
            ])
        return "\n".join(lines)

    def _best_page_excerpt(self, results: list[dict[str, str]]) -> tuple[str, str]:
        """Fetch one informative article, avoiding marketplace/search result pages."""
        blocked_domains = ("kleinanzeigen.", "suchen.mobile.", "dasparking.")
        candidates: list[tuple[int, int, dict[str, str]]] = []
        for index, result in enumerate(results):
            title = result.get("title", "").casefold()
            url = result.get("url", "")
            if not url or any(domain in url.casefold() for domain in blocked_domains):
                continue
            score = 0
            if "welche" in title or "welches" in title:
                score += 8
            if any(term in title for term in ("vergleich", "besten", "top ", "ratgeber")):
                score += 4
            if any(domain in url.casefold() for domain in
                   ("adac.de", "autoscout24.de", "stage-x-tuning.de")):
                score += 2
            candidates.append((score, -index, result))

        for _score, _order, result in sorted(candidates, reverse=True):
            try:
                page = self.fetch_url(
                    result["url"],
                    max_chars=max(12000, self.max_page_excerpt_chars * 3),
                )
                text = str(page.get("text", "")).strip()
                if len(text) >= 200:
                    focused = self._focus_excerpt(
                        text,
                        result.get("snippet", ""),
                        self.max_page_excerpt_chars,
                    )
                    return str(page.get("url", result["url"])), focused
            except Exception:
                logger.debug("Suchtreffer konnte nicht angereichert werden: %s",
                             result.get("url"), exc_info=True)
        return "", ""

    @staticmethod
    def _focus_excerpt(text: str, snippet: str, max_chars: int) -> str:
        """Center page text around its search snippet to discard menus/navigation."""
        compact = re.sub(r"\s+", " ", text).strip()
        anchor = re.sub(r"\s+", " ", snippet).strip()[:140]
        position = compact.casefold().find(anchor.casefold()) if len(anchor) >= 30 else -1
        if position < 0 and anchor:
            shorter = " ".join(anchor.split()[:8])
            position = compact.casefold().find(shorter.casefold())
        if position < 0:
            return compact[:max_chars]
        before = int(max_chars * 0.72)
        start = max(0, position - before)
        end = min(len(compact), start + max_chars)
        return compact[start:end].strip()

    @staticmethod
    def _relevant_excerpt(query: str, excerpt: str,
                          max_chars: int = 500) -> str:
        """Surface the source passage matching the user's actual constraints."""
        compact = re.sub(r"\s+", " ", excerpt).strip()
        if not compact:
            return ""

        query_terms = {
            term.casefold()
            for term in re.findall(r"[\wäöüß-]+", query, flags=re.UNICODE)
            if len(term) >= 5
        }
        ignored = {
            "welches", "welche", "eignet", "besten", "gebrauchtwagen",
            "modelle", "vergleich", "deutschland", "verfügbarkeit",
        }
        terms = [term for term in query_terms if term not in ignored]
        priority_stems = (
            "günstig", "erschwing", "budget", "preis", "kosten", "billig",
            "sicher", "schnell", "leicht", "klein", "groß", "aktuell",
        )
        ordered_terms = sorted(
            terms,
            key=lambda term: (
                any(term.startswith(stem) or stem.startswith(term)
                    for stem in priority_stems),
                len(term),
            ),
            reverse=True,
        )

        # lower() preserves character offsets; casefold() can expand ß to ss.
        folded = compact.lower()
        position = -1
        for term in ordered_terms:
            # A short stem also matches inflections such as günstig/günstige.
            stem = term[:max(5, min(len(term), 8))]
            position = folded.find(stem)
            if position >= 0:
                break
        if position < 0:
            return ""

        start = position
        end = min(len(compact), start + max_chars)
        selected = compact[start:end].strip()
        for boundary in (" Fazit:", " Relevant FAQ", " Mehr lesen", " Ähnliche Artikel"):
            if boundary in selected:
                selected = selected.split(boundary, 1)[0].strip()
        return selected

    @staticmethod
    def _example_evidence(excerpt: str, *, exclude_text: str = "",
                          max_groups: int = 5) -> str:
        """Extract category/example groups without mixing their properties."""
        compact = re.sub(r"\s+", " ", excerpt).strip()
        if not compact:
            return ""
        for boundary in (" Fazit:", " Relevant FAQ"):
            if boundary in compact:
                compact = compact.split(boundary, 1)[0]

        groups: list[str] = []
        for match in re.finditer(r"\bBeispiele:\s*[^.]{2,220}\.", compact):
            examples = match.group(0).strip()
            if examples and examples in exclude_text:
                continue

            previous_end = compact.rfind(". ", 0, match.start())
            group_start = compact.rfind(". ", 0, max(0, previous_end))
            start = group_start + 2 if group_start >= 0 else max(0, match.start() - 360)
            group = compact[start:match.end()].strip(" .") + "."
            if len(group) > 600:
                group = group[-600:].lstrip(" ,;:-")
            if group not in groups:
                groups.append(group)
            if len(groups) >= max_groups:
                break

        return "\n".join(f"- {group}" for group in groups)

    def _wikipedia_from_query(self, query: str) -> str:
        query = self._clean_search_query(query)
        data = self.wikipedia(query)
        if not data:
            return f"Kein Wikipedia-Eintrag für '{query}' gefunden."
        return (
            "WIKIPEDIA\n"
            f"Titel: {data['title']}\n"
            f"Beschreibung: {data['description']}\n"
            f"Zusammenfassung: {data['extract']}\n"
            f"Quelle: {data['url']}"
        )

    def _weather_from_location(self, location: str) -> str:
        location = location.strip() or "Kissing"
        data = self.weather(location)
        if not data:
            return (
                "WETTER_FEHLER\n"
                f"Ort: {location}\n"
                "Fehler: Der Wetterdienst lieferte keine aktuellen Daten."
            )
        return (
            "WETTER\n"
            f"Ort: {data['location']}\n"
            f"Temperatur: {data['temperature']} °C\n"
            f"Gefühlt: {data['feels_like']} °C\n"
            f"Wetter: {data['description']}\n"
            f"Luftfeuchtigkeit: {data['humidity']} %\n"
            f"Wind: {data['wind_kmh']} km/h\n"
            "Quelle: wttr.in"
        )

    def _url_from_value(self, url: str) -> str:
        url = url.strip()
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return "Keine gültige HTTP/HTTPS-URL erkannt."
        data = self.fetch_url(url)
        return (
            "WEBSEITE\n"
            f"URL: {data['url']}\n"
            f"Inhaltstyp: {data['content_type']}\n"
            f"Inhalt: {data['text']}"
        )

    def _handle_web_search(self, message: str) -> str:
        query = self._extract_search_query(message)
        if not query:
            return "Keine brauchbare Suchanfrage erkannt."

        results = self.search(query, max_results=self.max_results)
        if not results:
            return f"Keine Websuchergebnisse für: {query}"

        return self._format_search_results(query, results)

    def _handle_wikipedia(self, message: str) -> str:
        query = re.sub(r"\bwikipedia\b", "", message, flags=re.IGNORECASE)
        query = re.sub(r"\b(artikel|eintrag|seite)\b", "", query, flags=re.IGNORECASE)
        query = query.strip(" ?!.,:")
        data = self.wikipedia(query)
        if not data:
            return f"Kein Wikipedia-Eintrag für '{query}' gefunden."
        return (
            "WIKIPEDIA\n"
            f"Titel: {data['title']}\n"
            f"Beschreibung: {data['description']}\n"
            f"Zusammenfassung: {data['extract']}\n"
            f"Quelle: {data['url']}"
        )

    def _handle_weather(self, message: str) -> str:
        location = self._extract_weather_location(message)
        data = self.weather(location)
        if not data:
            return (
                "WETTER_FEHLER\n"
                f"Ort: {location}\n"
                "Fehler: Der Wetterdienst lieferte keine aktuellen Daten."
            )
        return (
            "WETTER\n"
            f"Ort: {data['location']}\n"
            f"Temperatur: {data['temperature']} °C\n"
            f"Gefühlt: {data['feels_like']} °C\n"
            f"Wetter: {data['description']}\n"
            f"Luftfeuchtigkeit: {data['humidity']} %\n"
            f"Wind: {data['wind_kmh']} km/h\n"
            "Quelle: wttr.in"
        )

    def _handle_url(self, message: str) -> str:
        match = re.search(r"https?://[^\s]+", message, re.IGNORECASE)
        if not match:
            return "Keine gültige URL erkannt."
        url = match.group(0).rstrip(".,!?)]}")
        data = self.fetch_url(url)
        return (
            "WEBSEITE\n"
            f"URL: {data['url']}\n"
            f"Inhaltstyp: {data['content_type']}\n"
            f"Inhalt: {data['text']}"
        )

    @staticmethod
    def _clean_search_query(query: str) -> str:
        query = re.sub(r"\s+", " ", query).strip()
        query = re.sub(r"^\s*(?:kannst du|könntest du|bitte)\s+", "", query, flags=re.IGNORECASE)
        query = query.strip(" ?!.,:")
        return query[:499]

    def _extract_search_query(self, message: str) -> str:
        patterns = (
            r"im internet(?: nach)?\s+(.+)$",
            r"im web(?: nach)?\s+(.+)$",
            r"online(?: nach)?\s+(.+)$",
            r"im netz(?: nach)?\s+(.+)$",
            r"(?:such|suche)\s+(?:im internet\s+)?(?:nach\s+)?(.+)$",
            r"recherchiere\s+(.+)$",
            r"aktuelle informationen(?: zu| über)?\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return self._clean_search_query(match.group(1))
        return self._clean_search_query(message)

    @staticmethod
    def _extract_weather_location(message: str) -> str:
        patterns = (
            r"wetter\s+(?:in|für)\s+(.+)$",
            r"temperatur\s+(?:in|für)\s+(.+)$",
            r"(?:regnet|regnen)\s+es\s+(?:in|bei)\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip(" ?!.,:")
        return "Kissing"

    def run_test(self) -> tuple[bool, str]:
        try:
            wiki = self.wikipedia("Wikipedia")
            if not wiki:
                return False, "Wikipedia-Test fehlgeschlagen."

            weather = self.weather("Kissing")
            if not weather:
                return False, "Wetter-Test fehlgeschlagen."

            results = self.search("BMW E46", max_results=1)
            if not results:
                return False, "Allgemeine Websuche lieferte keine Ergebnisse."

            return True, "WebSearchCore: Websuche, Wikipedia und Wetter einsatzbereit."
        except requests.RequestException as exc:
            return False, f"Netzwerkfehler: {exc}"
        except Exception as exc:
            logger.exception("WebSearchCore-Test fehlgeschlagen.")
            return False, f"Systemfehler: {exc}"
