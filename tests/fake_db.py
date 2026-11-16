"""In-memory repository for tests: same operations as the real one, no network.

It copies rows on the way in and on the way out, like a database would, so a
test cannot change stored data by mutating a result. It also fills in the two
defaults the app relies on the database for: a row `id` and a case number.
"""

import copy
import uuid
from datetime import UTC, datetime

from app.db import Row


class InMemoryRepository:
    """Holds tables as lists of dictionaries."""

    def __init__(self, tables: dict[str, list[Row]] | None = None) -> None:
        self._tables: dict[str, list[Row]] = copy.deepcopy(tables or {})
        self._case_sequence = 0

    def _matching(self, table: str, filters: Row | None) -> list[Row]:
        """Return the stored rows (not copies) whose columns equal the filters."""
        rows = self._tables.setdefault(table, [])
        wanted = (filters or {}).items()
        return [row for row in rows if all(row.get(col) == value for col, value in wanted)]

    def select(self, table: str, filters: Row | None = None) -> list[Row]:
        return copy.deepcopy(self._matching(table, filters))

    def insert(self, table: str, row: Row) -> Row:
        return self.insert_many(table, [row])[0]

    def insert_many(self, table: str, rows: list[Row]) -> list[Row]:
        stored = []
        for row in rows:
            new_row = copy.deepcopy(row)
            if table != "insurance_products":
                new_row.setdefault("id", str(uuid.uuid4()))
            if table == "cases" and "case_number" not in new_row:
                self._case_sequence += 1
                new_row["case_number"] = f"MG-{datetime.now(UTC).year}-{self._case_sequence:06d}"
            self._tables.setdefault(table, []).append(new_row)
            stored.append(copy.deepcopy(new_row))
        return stored

    def update(self, table: str, filters: Row, values: Row) -> list[Row]:
        matched = self._matching(table, filters)
        for row in matched:
            row.update(copy.deepcopy(values))
        return copy.deepcopy(matched)

    def delete_all(self, table: str, key: str = "id") -> None:
        self._tables[table] = []

    def ping(self) -> bool:
        return True
