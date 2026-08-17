from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import (
    parse_qs,
    quote,
    urlparse,
)

import requests
from bs4 import BeautifulSoup

from module.base_module import ModuleBase
from module.search_query_llm import SearchQueryLLM


class WebSearchModule(ModuleBase):

    @property
    def name(self) -> str:
        return "WebSearchCore"

    def __init__(
        self,
        config: dict | None = None,
    ) -> None:

        self.config = config or {}

        self.max_results = int(
            self.config.get(
                "web_search_max_results",
                5,
            )
        )

        self.timeout = int(
            self.config.get(
                "web_search_timeout",
                10,
            )
        )

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "EVA/1.0 "
                    "(personal AI assistant)"
                ),
                "Accept-Language": (
                    "de-DE,de;q=0.9,en;q=0.8"
                ),
            }
        )

    def can_handle(
        self,
        message: str,
    ) -> bool:
        return False

    # =========================================================
    # HAUPTFUNKTION
    # =========================================================

    def handle(
        self,
        message: str,
        context: dict,
    ) -> dict:

        search_query = message.strip()

        logging.info(
            "[%s] Recherche gestartet.",
            self.name,
        )

        logging.info(
            "[%s] Suchanfrage: %s",
            self.name,
            search_query,
        )

        if not search_query:

            return {
                "text": (
                    "Keine Suchanfrage vorhanden."
                ),
                "query": "",
                "results": [],
            }

        results = self._search_duckduckgo(
            search_query
        )

        results.extend(
            self._search_wikipedia(
                search_query
            )
        )

        results = self._deduplicate(
            results
        )

        results = results[
            : self.max_results
        ]

        if not results:

            return {
                "text": (
                    "[System-Meldung: Websuche durchgeführt]\n\n"
                    f"Suchanfrage: {search_query}\n\n"
                    "Es wurden keine relevanten Ergebnisse gefunden."
                ),
                "query": search_query,
                "results": [],
            }

        return {
            "text": self._build_context(
                search_query,
                results,
            ),
            "query": search_query,
            "results": results,
        }

    # =========================================================
    # DUCKDUCKGO
    # =========================================================

    def _search_duckduckgo(
        self,
        query: str,
    ) -> list[dict]:

        try:

            response = self.session.get(
                "https://html.duckduckgo.com/html/",
                params={
                    "q": query,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.RequestException as exc:

            logging.error(
                "[%s] DuckDuckGo Fehler: %s",
                self.name,
                exc,
            )

            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        results: list[dict] = []

        for result in soup.select(
            ".result"
        ):

            title_element = result.select_one(
                ".result__title"
            )

            link_element = result.select_one(
                ".result__a"
            )

            snippet_element = result.select_one(
                ".result__snippet"
            )

            if not title_element or not link_element:
                continue

            title = self._clean_text(
                title_element.get_text(
                    " ",
                    strip=True,
                )
            )

            raw_url = (
                link_element.get(
                    "href",
                    "",
                )
                or ""
            )

            url = self._extract_real_url(
                raw_url
            )

            snippet = ""

            if snippet_element:

                snippet = self._clean_text(
                    snippet_element.get_text(
                        " ",
                        strip=True,
                    )
                )

            if not title or not url:
                continue

            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": self._domain(url),
                }
            )

            if len(results) >= self.max_results:
                break

        return results

    # =========================================================
    # WIKIPEDIA
    # =========================================================

    def _search_wikipedia(
        self,
        query: str,
    ) -> list[dict]:

        try:

            response = self.session.get(
                "https://de.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 2,
                    "utf8": 1,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()

            data = response.json()

        except Exception as exc:

            logging.warning(
                "[%s] Wikipedia-Suche fehlgeschlagen: %s",
                self.name,
                exc,
            )

            return []

        results: list[dict] = []

        for item in (
            data
            .get("query", {})
            .get("search", [])
        ):

            title = item.get(
                "title",
                "",
            )

            snippet = self._clean_text(
                item.get(
                    "snippet",
                    "",
                )
            )

            if not title:
                continue

            url = (
                "https://de.wikipedia.org/wiki/"
                + quote(
                    title.replace(
                        " ",
                        "_",
                    )
                )
            )

            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": "Wikipedia",
                }
            )

        return results

    # =========================================================
    # CONTEXT
    # =========================================================

    def _build_context(
        self,
        query: str,
        results: list[dict],
    ) -> str:

        lines = [
            "[System-Meldung: Websuche durchgeführt]",
            "",
            f"SUCHANFRAGE: {query}",
            "",
            "RECHERCHEERGEBNISSE:",
            "",
        ]

        for index, result in enumerate(
            results,
            start=1,
        ):

            lines.append(
                f"[{index}] "
                f"{result.get('title', 'Ohne Titel')}"
            )

            lines.append(
                f"Quelle: "
                f"{result.get('source', '')}"
            )

            lines.append(
                f"URL: "
                f"{result.get('url', '')}"
            )

            snippet = result.get(
                "snippet",
                "",
            )

            if snippet:
                lines.append(
                    f"Auszug: {snippet}"
                )

            lines.append("")

        lines.append(
            "Nutze die Recherche als Informationsquelle. "
            "Erfinde keine zusätzlichen Fakten."
        )

        return "\n".join(
            lines
        )

    # =========================================================
    # HILFSFUNKTIONEN
    # =========================================================

    @staticmethod
    def _clean_text(
        text: str,
    ) -> str:

        text = BeautifulSoup(
            unescape(text),
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    @staticmethod
    def _extract_real_url(
        url: str,
    ) -> str:

        if not url:
            return ""

        try:

            parsed = urlparse(
                url
            )

            params = parse_qs(
                parsed.query
            )

            if "uddg" in params:

                return params[
                    "uddg"
                ][0]

            return url

        except Exception:

            return url

    @staticmethod
    def _domain(
        url: str,
    ) -> str:

        try:
            return urlparse(
                url
            ).netloc

        except Exception:
            return "Web"

    @staticmethod
    def _deduplicate(
        results: list[dict],
    ) -> list[dict]:

        seen: set[str] = set()
        unique: list[dict] = []

        for result in results:

            url = result.get(
                "url",
                "",
            ).strip()

            if not url:
                continue

            if url in seen:
                continue

            seen.add(url)
            unique.append(
                result
            )

        return unique

    # =========================================================
    # MODULTEST
    # =========================================================

    def run_test(
        self,
    ) -> tuple[bool, str]:

        try:

            response = self.session.get(
                "https://de.wikipedia.org/api/rest_v1/page/summary/Wikipedia",
                timeout=4,
            )

            if response.status_code == 200:

                return (
                    True,
                    "Websuche erreichbar.",
                )

            return (
                False,
                f"HTTP {response.status_code}",
            )

        except Exception as exc:

            return (
                False,
                f"Verbindungsfehler: {exc}",
            )