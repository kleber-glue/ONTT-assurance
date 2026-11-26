import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS oracle_configuration (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    table_name TEXT,
    update_column TEXT,
    identifier_column TEXT,
    adherent_column TEXT,
    bulletin_column TEXT,
    bordereau_column TEXT,
    oracle_type TEXT,
    complementary_where TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oracle_correspondences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT,
    error_type INTEGER,
    update_column TEXT,
    identifier_column TEXT,
    adherent_column TEXT,
    bulletin_column TEXT,
    bordereau_column TEXT,
    oracle_type TEXT,
    complementary_where TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oracle_correspondence_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oracle_correspondence_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correspondence_id INTEGER NOT NULL,
    table_name TEXT,
    update_column TEXT,
    identifier_column TEXT,
    adherent_column TEXT,
    bulletin_column TEXT,
    bordereau_column TEXT,
    oracle_type TEXT,
    complementary_where TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (correspondence_id)
        REFERENCES oracle_correspondence_groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS error_rules (
    code INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    table_name TEXT,
    update_column TEXT,
    identifier_column TEXT,
    complement TEXT,
    oracle_type TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    numero_bordereau TEXT,
    annee INTEGER,
    total_records INTEGER NOT NULL,
    valid_records INTEGER NOT NULL DEFAULT 0,
    invalid_records INTEGER NOT NULL DEFAULT 0,
    sql_filename TEXT,
    sql_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO oracle_configuration (id, oracle_type)
VALUES (1, 'VARCHAR2');

INSERT OR IGNORE INTO error_rules (code, label, active) VALUES
    (1, 'Couple', 0),
    (2, 'Erreur de saisie', 0),
    (3, 'Numéro bulletin commençant par 0', 0),
    (9, 'Numéro Bordereaux', 0);
"""


def get_connection(database_path):
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(database_path):
    with get_connection(database_path) as connection:
        connection.executescript(SCHEMA)
        correspondence_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(oracle_correspondences)"
            ).fetchall()
        }
        if "error_type" not in correspondence_columns:
            connection.execute(
                "ALTER TABLE oracle_correspondences ADD COLUMN error_type INTEGER"
            )
        correspondence_count = connection.execute(
            "SELECT COUNT(*) FROM oracle_correspondences"
        ).fetchone()[0]
        legacy_configuration = connection.execute(
            "SELECT * FROM oracle_configuration WHERE id = 1"
        ).fetchone()
        if (
            correspondence_count == 0
            and legacy_configuration
            and legacy_configuration["table_name"]
        ):
            connection.execute(
                """
                INSERT INTO oracle_correspondences
                (table_name, update_column, identifier_column, adherent_column,
                 bulletin_column, bordereau_column, oracle_type, complementary_where)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(
                    legacy_configuration[field]
                    for field in (
                        "table_name", "update_column", "identifier_column",
                        "adherent_column", "bulletin_column", "bordereau_column",
                        "oracle_type", "complementary_where",
                    )
                ),
            )
            connection.execute(
                "UPDATE oracle_configuration SET table_name = NULL WHERE id = 1"
            )

        group_count = connection.execute(
            "SELECT COUNT(*) FROM oracle_correspondence_groups"
        ).fetchone()[0]
        if group_count == 0:
            legacy_correspondences = connection.execute(
                "SELECT * FROM oracle_correspondences ORDER BY id"
            ).fetchall()
            for correspondence in legacy_correspondences:
                cursor = connection.execute(
                    "INSERT INTO oracle_correspondence_groups (error_type) VALUES (?)",
                    (correspondence["error_type"],),
                )
                connection.execute(
                    """
                    INSERT INTO oracle_correspondence_tables
                    (correspondence_id, table_name, update_column, identifier_column,
                     adherent_column, bulletin_column, bordereau_column, oracle_type,
                     complementary_where)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cursor.lastrowid,
                        correspondence["table_name"],
                        correspondence["update_column"],
                        correspondence["identifier_column"],
                        correspondence["adherent_column"],
                        correspondence["bulletin_column"],
                        correspondence["bordereau_column"],
                        correspondence["oracle_type"],
                        correspondence["complementary_where"],
                    ),
                )
            if legacy_correspondences:
                connection.execute("DELETE FROM oracle_correspondences")
