"""
Monday.com API v2 (GraphQL) client.

Design notes (see DECISION_LOG.md for full rationale):
- Uses the direct GraphQL API rather than monday.com's MCP server. For a
  single hosted Streamlit process, shelling out to / managing a separate MCP
  server process adds deployment complexity without adding capability here.
- Read-only: only queries are issued, never mutations, per the assignment's
  "Monday.com — Read only" integration requirement.
- Pagination via `items_page` + cursor, since monday.com boards can exceed
  the 500-item single-page limit.
- No CSV data is ever hardcoded here — every call hits the live API.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

MONDAY_API_URL = "https://api.monday.com/v2"
API_VERSION = "2024-10"  # pinned so column_values shape doesn't shift under us

BOARDS_SCHEMA_QUERY = """
query GetBoardsSchema($boardIds: [ID!]) {
  boards(ids: $boardIds) {
    id
    name
    columns {
      id
      title
      type
    }
    items_count
  }
}
"""

ITEMS_PAGE_QUERY = """
query GetItemsPage($boardId: ID!, $cursor: String, $limit: Int!) {
  boards(ids: [$boardId]) {
    items_page(limit: $limit, cursor: $cursor) {
      cursor
      items {
        id
        name
        column_values {
          id
          text
          value
          column {
            title
            type
          }
        }
      }
    }
  }
}
"""


class MondayAPIError(RuntimeError):
    """Raised for auth failures, GraphQL errors, or exhausted retries."""


@dataclass
class BoardSchema:
    board_id: str
    name: str
    columns: list[dict] = field(default_factory=list)
    items_count: int = 0


class MondayClient:
    def __init__(self, api_token: Optional[str] = None, timeout: int = 20):
        self.api_token = api_token or os.environ.get("MONDAY_API_TOKEN")
        if not self.api_token:
            raise MondayAPIError(
                "No monday.com API token found. Set MONDAY_API_TOKEN in the "
                "environment (Admin > API in your monday.com account)."
            )
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": self.api_token,
                "Content-Type": "application/json",
                "API-Version": API_VERSION,
            }
        )

    def _post(self, query: str, variables: dict, max_retries: int = 3) -> dict:
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                resp = self._session.post(
                    MONDAY_API_URL,
                    json={"query": query, "variables": variables},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if resp.status_code == 401:
                raise MondayAPIError(
                    "monday.com rejected the API token (401). Check "
                    "MONDAY_API_TOKEN is current and has board read access."
                )
            if resp.status_code == 429:
                # Rate limited — back off and retry.
                retry_after = int(resp.headers.get("Retry-After", 2**attempt))
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                last_error = MondayAPIError(f"monday.com server error {resp.status_code}")
                time.sleep(2**attempt)
                continue

            payload = resp.json()
            if "errors" in payload and payload["errors"]:
                raise MondayAPIError(f"GraphQL error: {payload['errors']}")
            return payload["data"]

        raise MondayAPIError(
            f"monday.com API unreachable after {max_retries} attempts: {last_error}"
        )

    def get_boards_schema(self, board_ids: list[str]) -> list[BoardSchema]:
        """Fetch column layout for the given boards. Used so the agent can
        reason about what fields actually exist instead of assuming a fixed
        schema."""
        data = self._post(BOARDS_SCHEMA_QUERY, {"boardIds": board_ids})
        boards = data.get("boards") or []
        return [
            BoardSchema(
                board_id=b["id"],
                name=b["name"],
                columns=b["columns"],
                items_count=b.get("items_count", 0),
            )
            for b in boards
        ]

    def get_all_items(self, board_id: str, page_limit: int = 100) -> list[dict[str, Any]]:
        """Fetch every item on a board as a flat dict: {"name": ..., "<column
        title>": <text value>, ...}. Pagination-safe for boards > 100 rows."""
        items: list[dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            data = self._post(
                ITEMS_PAGE_QUERY,
                {"boardId": board_id, "cursor": cursor, "limit": page_limit},
            )
            boards = data.get("boards") or []
            if not boards:
                break
            items_page = boards[0]["items_page"]

            for item in items_page["items"]:
                row: dict[str, Any] = {"_item_id": item["id"], "name": item["name"]}
                for cv in item["column_values"]:
                    title = cv["column"]["title"]
                    row[title] = cv["text"]
                items.append(row)

            cursor = items_page.get("cursor")
            if not cursor:
                break

        return items

    def ping(self) -> str:
        """Lightweight connectivity/auth check for a startup health check."""
        data = self._post("query { me { name } }", {})
        return data["me"]["name"]
