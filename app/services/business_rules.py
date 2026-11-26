from app.models.database import get_connection


def load_rules(database_path):
    with get_connection(database_path) as connection:
        rows = connection.execute("SELECT * FROM error_rules").fetchall()
        return {
            row["code"]: {
                "label": row["label"],
                "active": bool(row["active"]),
                "table_name": row["table_name"],
                "update_column": row["update_column"],
                "identifier_column": row["identifier_column"],
                "complement": row["complement"],
                "oracle_type": row["oracle_type"],
            }
            for row in rows
        }


def save_rule(database_path, code, values):
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE error_rules
            SET active = ?, table_name = ?, update_column = ?,
                identifier_column = ?, complement = ?, oracle_type = ?, updated_at = CURRENT_TIMESTAMP
            WHERE code = ?
            """,
            (
                1 if values["active"] else 0,
                values["table_name"].strip() or None,
                values["update_column"].strip() or None,
                values["identifier_column"].strip() or None,
                values["complement"].strip() or None,
                values["oracle_type"].strip() or None,
                code,
            ),
        )
