import sqlite3
from pathlib import Path

from app import create_app
from app.models.database import get_connection, init_database
from app.services.excel_reader import read_excel
from app.services.json_processor import build_json_payload
from app.services.data_validator import validate_records
from app.services.sql_generator import oracle_literal, generate_sql


SOURCE = Path(r"e:\ONTT\Bordereaux\Assurance reunion\etat.xlsx")


def test_legacy_oracle_configuration_is_migrated_to_correspondence(tmp_path):
    database_path = tmp_path / "app.db"
    init_database(database_path)
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE oracle_configuration
            SET table_name = 'OLD_TABLE', update_column = 'OLD_VALUE',
                identifier_column = 'OLD_ID'
            WHERE id = 1
            """
        )

    init_database(database_path)

    with get_connection(database_path) as connection:
        correspondence = connection.execute(
            """
            SELECT g.error_type, t.table_name, t.update_column, t.identifier_column
            FROM oracle_correspondence_groups g
            JOIN oracle_correspondence_tables t ON t.correspondence_id = g.id
            """
        ).fetchone()
    assert tuple(correspondence) == (None, "OLD_TABLE", "OLD_VALUE", "OLD_ID")

    with get_connection(database_path) as connection:
        connection.execute("DELETE FROM oracle_correspondence_groups")
    init_database(database_path)
    with get_connection(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM oracle_correspondence_groups"
        ).fetchone()[0]
    assert count == 0


def test_existing_correspondence_table_gets_error_type_column(tmp_path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE oracle_correspondences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT,
                update_column TEXT,
                identifier_column TEXT,
                adherent_column TEXT,
                bulletin_column TEXT,
                bordereau_column TEXT,
                oracle_type TEXT,
                complementary_where TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO oracle_correspondences (table_name) VALUES ('OLD_TABLE')"
        )

    init_database(database_path)

    with get_connection(database_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(oracle_correspondences)"
            ).fetchall()
        }
        correspondence = connection.execute(
            """
            SELECT g.error_type, t.table_name
            FROM oracle_correspondence_groups g
            JOIN oracle_correspondence_tables t ON t.correspondence_id = g.id
            """
        ).fetchone()
    assert "error_type" in columns
    assert tuple(correspondence) == (None, "OLD_TABLE")


def test_configuration_hides_error_rules_without_overwriting_them(tmp_path):
    class TestConfig:
        SECRET_KEY = "test"
        MAX_CONTENT_LENGTH = 10 * 1024 * 1024
        UPLOAD_FOLDER = tmp_path / "uploads"
        SQL_FOLDER = tmp_path / "generated"
        DATABASE_PATH = tmp_path / "app.db"

    app = create_app(TestConfig)
    with get_connection(TestConfig.DATABASE_PATH) as connection:
        connection.execute(
            "UPDATE error_rules SET active = 1, table_name = 'EXISTING_TABLE' WHERE code = 1"
        )

    client = app.test_client()
    response = client.get("/configuration")
    assert b"R\xc3\xa8gles par code erreur" not in response.data
    assert b'id="add-correspondence"' in response.data
    assert b'id="correspondence-template"' in response.data
    assert b"add-table" in response.data
    assert b'class="table-template"' in response.data

    response = client.post(
        "/configuration",
        data={
            "correspondence_ids": ["0", "1"],
            "correspondences[0][error_type]": "1",
            "correspondences[0][table_ids]": ["0", "1"],
            "correspondences[0][tables][0][table_name]": "NEW_TABLE",
            "correspondences[0][tables][0][oracle_type]": "VARCHAR2",
            "correspondences[0][tables][1][table_name]": "POLICY_TABLE",
            "correspondences[0][tables][1][oracle_type]": "VARCHAR2",
            "correspondences[1][error_type]": "9",
            "correspondences[1][table_ids]": "0",
            "correspondences[1][tables][0][table_name]": "ARCHIVE_TABLE",
            "correspondences[1][tables][0][oracle_type]": "VARCHAR2",
        },
    )
    assert response.status_code == 302
    with get_connection(TestConfig.DATABASE_PATH) as connection:
        rule = connection.execute(
            "SELECT active, table_name FROM error_rules WHERE code = 1"
        ).fetchone()
        correspondences = connection.execute(
            """
            SELECT g.error_type, t.table_name
            FROM oracle_correspondence_groups g
            JOIN oracle_correspondence_tables t ON t.correspondence_id = g.id
            ORDER BY g.id
            """
        ).fetchall()
    assert rule["active"] == 1
    assert rule["table_name"] == "EXISTING_TABLE"
    assert [tuple(row) for row in correspondences] == [
        (1, "NEW_TABLE"), (1, "POLICY_TABLE"), (9, "ARCHIVE_TABLE"),
    ]
    response = client.get("/configuration")
    page = response.get_data(as_text=True)
    assert 'value="NEW_TABLE"' in page
    assert 'value="POLICY_TABLE"' in page


def test_configuration_rejects_invalid_oracle_column_names(tmp_path):
    class TestConfig:
        SECRET_KEY = "test"
        MAX_CONTENT_LENGTH = 10 * 1024 * 1024
        UPLOAD_FOLDER = tmp_path / "uploads"
        SQL_FOLDER = tmp_path / "generated"
        DATABASE_PATH = tmp_path / "app.db"

    app = create_app(TestConfig)
    client = app.test_client()
    response = client.post(
        "/configuration",
        data={
            "correspondence_ids": ["0"],
            "correspondences[0][error_type]": "1",
            "correspondences[0][table_ids]": "0",
            "correspondences[0][tables][0][table_name]": "BULL_START",
            "correspondences[0][tables][0][update_column]": "Règles par code erreur",
            "correspondences[0][tables][0][identifier_column]": "NUM_SATRT",
            "correspondences[0][tables][0][adherent_column]": "ADHERENT",
            "correspondences[0][tables][0][bulletin_column]": "NUM_BULLETIN",
            "correspondences[0][tables][0][bordereau_column]": "9",
            "correspondences[0][tables][0][oracle_type]": "VARCHAR2",
        },
    )

    assert response.status_code == 400
    assert "Colonne de mise à jour" in response.get_data(as_text=True)
    assert "Règles par code erreur" in response.get_data(as_text=True)
    response = client.post(
        "/configuration",
        data={
            "correspondence_ids": ["0"],
            "correspondences[0][error_type]": "1",
            "correspondences[0][table_ids]": "0",
            "correspondences[0][tables][0][table_name]": "BULL_START",
            "correspondences[0][tables][0][update_column]": "NUM_BULLETIN",
            "correspondences[0][tables][0][identifier_column]": "NUM_SATRT",
            "correspondences[0][tables][0][adherent_column]": "ADHERENT",
            "correspondences[0][tables][0][bulletin_column]": "NUM_BULLETIN",
            "correspondences[0][tables][0][bordereau_column]": "9",
            "correspondences[0][tables][0][oracle_type]": "VARCHAR2",
        },
    )
    assert response.status_code == 400
    assert "Colonne numéro bordereau" in response.get_data(as_text=True)
    assert "« 9 »" in response.get_data(as_text=True)
    with get_connection(TestConfig.DATABASE_PATH) as connection:
        correspondences = connection.execute(
            "SELECT COUNT(*) FROM oracle_correspondence_groups"
        ).fetchone()[0]
    assert correspondences == 0


def test_configuration_error_type_options_come_from_json(tmp_path):
    class TestConfig:
        SECRET_KEY = "test"
        MAX_CONTENT_LENGTH = 10 * 1024 * 1024
        UPLOAD_FOLDER = tmp_path / "uploads"
        SQL_FOLDER = tmp_path / "generated"
        DATABASE_PATH = tmp_path / "app.db"

    app = create_app(TestConfig)
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["payload"] = {
            "records": [
                {"type_erreur": 2},
                {"type_erreur": 9},
                {"type_erreur": 2},
            ]
        }

    response = client.get("/configuration")
    page = response.get_data(as_text=True)
    assert 'value="2"' in page
    assert 'value="9"' in page
    assert "1 - Couple" not in page


def test_t01_to_t05_real_excel_analysis():
    extracted = read_excel(SOURCE)
    assert extracted["sheets"] == ["2026"]
    assert extracted["sheet"] == "2026"
    assert len(extracted["records"]) == 10
    assert extracted["records"][4]["num_bulletin"] == "01376304"
    assert extracted["records"][5]["num_bulletin"] == "01290415"
    assert extracted["records"][8]["num_bulletin"] == "01152284"


def test_t06_to_t10_json_validation():
    extracted = read_excel(SOURCE)
    payload = build_json_payload(extracted, "9", 2026)
    assert payload["metadata"]["numero_bordereau"] == "9"
    assert payload["metadata"]["annee"] == 2026
    assert all("numero_bordereau" not in row for row in payload["records"])

    rules = {code: {"active": False} for code in (1, 2, 3, 9)}
    validated = validate_records(payload["records"], rules)
    assert all(row["status"] == "ERROR" for row in validated)
    unknown = dict(payload["records"][0])
    unknown["type_erreur"] = 77
    assert "Code erreur inconnu." in validate_records([unknown], rules)[0]["errors"]


def test_t11_missing_rule_blocks_sql():
    record = {
        "ligne": "1",
        "adherent": "2193",
        "num_bulletin": "1366856",
        "type_erreur": 1,
        "correction_proposee": "9365",
    }
    rules = {1: {"active": False}}
    validated = validate_records([record], rules)
    global_config = {
        "table_name": "DONNEES_ASSURANCE",
        "update_column": "NUM_BULLETIN",
        "identifier_column": "LIGNE_ETAT",
        "adherent_column": "ADHERENT",
        "bulletin_column": "NUM_BULLETIN",
        "bordereau_column": "NUM_BORDEREAU",
        "oracle_type": "VARCHAR2",
        "complementary_where": None,
    }
    statements, rejected = generate_sql(
        {"metadata": {"numero_bordereau": "9", "annee": 2026}},
        validated,
        rules,
        global_config,
    )
    assert statements == []


def test_t12_to_t14_sql_security_and_apostrophe():
    assert oracle_literal("O'Brien") == "'O''Brien'"
    try:
        oracle_literal("abc", "NUMBER")
        assert False
    except ValueError:
        pass

    record = {
        "ligne": "1",
        "adherent": "2193",
        "num_bulletin": "1366856",
        "type_erreur": 1,
        "correction_proposee": "9365",
        "status": "VALID",
        "errors": [],
        "warnings": [],
    }
    rule = {
        "active": True,
        "update_column": "NUM_BULLETIN",
        "identifier_column": "LIGNE_ETAT",
        "complement": None,
        "oracle_type": "VARCHAR2",
    }
    rules = {1: rule}
    global_config = {
        "table_name": "DONNEES_ASSURANCE",
        "update_column": None,
        "identifier_column": None,
        "adherent_column": "ADHERENT",
        "bulletin_column": "NUM_BULLETIN",
        "bordereau_column": "NUM_BORDEREAU",
        "oracle_type": "VARCHAR2",
        "complementary_where": None,
    }
    payload = {
        "metadata": {
            "numero_bordereau": "9",
            "annee": 2026,
        }
    }
    statements, rejected = generate_sql(payload, [record], rules, global_config)
    assert len(statements) == 1
    assert "WHERE " in statements[0]
    assert "ADHERENT = '2193'" in statements[0]

    second_correspondence = dict(global_config, table_name="ARCHIVE_TABLE")
    statements, rejected = generate_sql(
        payload,
        [record],
        rules,
        [global_config, second_correspondence],
    )
    assert len(statements) == 2
    assert statements[0].startswith("UPDATE DONNEES_ASSURANCE")
    assert statements[1].startswith("UPDATE ARCHIVE_TABLE")


def test_correspondence_generates_sql_only_for_its_json_error_type():
    record_template = {
        "ligne": "1",
        "adherent": "2193",
        "num_bulletin": "1366856",
        "correction_proposee": "9365",
        "status": "VALID",
    }
    records = [
        dict(record_template, type_erreur=1),
        dict(record_template, ligne="2", type_erreur=2),
    ]
    rules = {
        code: {
            "active": True,
            "update_column": "NUM_BULLETIN",
            "identifier_column": "LIGNE_ETAT",
            "complement": None,
            "oracle_type": "VARCHAR2",
        }
        for code in (1, 2)
    }
    correspondence = {
        "table_name": "TARGET_TABLE",
        "error_type": 2,
        "adherent_column": "ADHERENT",
        "oracle_type": "VARCHAR2",
    }
    payload = {"metadata": {"numero_bordereau": "9"}}

    statements, rejected = generate_sql(payload, records, rules, [correspondence])

    assert len(statements) == 1
    assert "UPDATE TARGET_TABLE" in statements[0]
    assert "LIGNE_ETAT = '2'" in statements[0]
    assert rejected == []


def test_correspondence_generates_updates_for_each_nested_table():
    record = {
        "ligne": "1",
        "adherent": "2193",
        "num_bulletin": "1366856",
        "type_erreur": 1,
        "correction_proposee": "9365",
        "status": "VALID",
    }
    rule = {
        "active": True,
        "update_column": "NUM_BULLETIN",
        "identifier_column": "LIGNE_ETAT",
        "complement": None,
        "oracle_type": "VARCHAR2",
    }
    group = {
        "error_type": 1,
        "tables": [
            {"table_name": "BULL_START"},
            {"table_name": "BULL_HISTORY"},
        ],
    }

    statements, rejected = generate_sql(
        {"metadata": {"numero_bordereau": "9"}},
        [record],
        {1: rule},
        [group],
    )

    assert len(statements) == 2
    assert statements[0].startswith("UPDATE BULL_START")
    assert statements[1].startswith("UPDATE BULL_HISTORY")
    assert rejected == []
