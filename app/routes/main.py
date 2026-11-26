from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, send_file, session, url_for,
)
from werkzeug.utils import secure_filename

from app.models.database import get_connection
from app.services.business_rules import load_rules
from app.services.data_validator import validate_records
from app.services.excel_reader import ExcelReaderError, read_excel
from app.services.json_processor import build_json_payload
from app.services.sql_generator import (
    build_sql_document,
    generate_sql,
    validate_oracle_identifier_fields,
)


bp = Blueprint("main", __name__)


def db_path():
    return current_app.config["DATABASE_PATH"]


def get_oracle_correspondences():
    with get_connection(db_path()) as connection:
        groups = connection.execute(
            "SELECT * FROM oracle_correspondence_groups ORDER BY id"
        ).fetchall()
        correspondences = []
        for group in groups:
            correspondence = dict(group)
            tables = connection.execute(
                """
                SELECT * FROM oracle_correspondence_tables
                WHERE correspondence_id = ? ORDER BY id
                """,
                (group["id"],),
            ).fetchall()
            correspondence["tables"] = [dict(table) for table in tables]
            correspondences.append(correspondence)
        return correspondences


def get_available_error_types():
    rules = load_rules(db_path())
    source = session.get("payload") or session.get("extracted")
    records = source.get("records") if source else None
    codes = []
    if records is None:
        codes = [str(code) for code in rules]
    else:
        for record in records:
            value = record.get("type_erreur")
            code = str(value).strip() if value is not None else ""
            if code and code not in codes:
                codes.append(code)

    error_types = []
    for code in codes:
        try:
            rule = rules.get(int(code))
        except ValueError:
            rule = None
        label = rule["label"] if rule else f"Code erreur {code}"
        error_types.append({"code": code, "label": f"{code} - {label}"})
    return error_types


def parse_correspondences(form):
    table_fields = [
        "table_name", "update_column", "identifier_column",
        "adherent_column", "bulletin_column", "bordereau_column",
        "oracle_type", "complementary_where",
    ]
    correspondences = []
    seen_indexes = set()
    for index in form.getlist("correspondence_ids"):
        if not index.isdigit() or index in seen_indexes:
            raise ValueError("La liste des correspondances Oracle est invalide.")
        seen_indexes.add(index)
        error_type = (
            form.get(f"correspondences[{index}][error_type]") or ""
        ).strip()
        if error_type:
            if not error_type.isdigit():
                raise ValueError("Le type d'erreur doit être un code numérique.")
            error_type = int(error_type)

        tables = []
        table_indexes = form.getlist(f"correspondences[{index}][table_ids]")
        seen_table_indexes = set()
        for table_index in table_indexes:
            if not table_index.isdigit() or table_index in seen_table_indexes:
                raise ValueError("La liste des tables Oracle est invalide.")
            seen_table_indexes.add(table_index)
            table = {
                field: (
                    form.get(
                        f"correspondences[{index}][tables][{table_index}][{field}]"
                    ) or ""
                ).strip() or None
                for field in table_fields
            }
            if any(table.values()):
                tables.append(table)

        if error_type is not None or tables:
            if not tables:
                raise ValueError(
                    "Ajoutez au moins une table à chaque correspondance globale."
                )
            correspondence = {"error_type": error_type, "tables": tables}
            correspondences.append(correspondence)
    return correspondences


def save_oracle_correspondences(correspondences):
    with get_connection(db_path()) as connection:
        connection.execute("DELETE FROM oracle_correspondence_tables")
        connection.execute("DELETE FROM oracle_correspondence_groups")
        for correspondence in correspondences:
            cursor = connection.execute(
                """
                INSERT INTO oracle_correspondence_groups (error_type)
                VALUES (?)
                """,
                (correspondence["error_type"],),
            )
            for table in correspondence["tables"]:
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
                        *(
                            table[field]
                            for field in (
                                "table_name", "update_column", "identifier_column",
                                "adherent_column", "bulletin_column", "bordereau_column",
                                "oracle_type", "complementary_where",
                            )
                        ),
                    ),
                )


@bp.route("/")
def dashboard():
    with get_connection(db_path()) as connection:
        history = connection.execute(
            "SELECT * FROM processing_history ORDER BY id DESC LIMIT 10"
        ).fetchall()
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS traitements,
                COUNT(DISTINCT source_file) AS fichiers,
                COALESCE(SUM(total_records), 0) AS lignes,
                COALESCE(SUM(valid_records), 0) AS valides,
                COALESCE(SUM(invalid_records), 0) AS rejetees,
                COALESCE(SUM(sql_count), 0) AS scripts
            FROM processing_history
            """
        ).fetchone()
    return render_template("dashboard.html", history=history, totals=totals)


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        uploaded = request.files.get("excel_file")
        selected_sheet = request.form.get("sheet")
        if not uploaded or not uploaded.filename:
            flash("Veuillez sélectionner un fichier Excel.", "danger")
            return redirect(url_for("main.upload"))
        if Path(uploaded.filename).suffix.lower() != ".xlsx":
            flash("Seuls les fichiers XLSX sont acceptés.", "danger")
            return redirect(url_for("main.upload"))

        filename = secure_filename(uploaded.filename)
        destination = current_app.config["UPLOAD_FOLDER"] / filename
        uploaded.save(destination)
        try:
            extracted = read_excel(destination, selected_sheet or None)
        except ExcelReaderError as error:
            flash(str(error), "danger")
            return redirect(url_for("main.upload"))

        session["extracted"] = extracted
        session.pop("payload", None)
        session.pop("validated", None)
        session.pop("sql_document", None)
        flash("Fichier importé et colonnes vérifiées.", "success")
        return redirect(url_for("main.bordereau"))
    return render_template("upload.html")


@bp.route("/bordereau", methods=["GET", "POST"])
def bordereau():
    extracted = session.get("extracted")
    if not extracted:
        flash("Importez d'abord un fichier Excel.", "warning")
        return redirect(url_for("main.upload"))

    if request.method == "POST":
        numero = request.form.get("numero_bordereau", "").strip()
        annee = request.form.get("annee", "").strip()
        if not numero or not annee.isdigit():
            flash("Le numéro du bordereau et une année valide sont obligatoires.", "danger")
            return redirect(url_for("main.bordereau"))
        year = int(annee)
        if not 1900 <= year <= 2200:
            flash("L'année doit être comprise entre 1900 et 2200.", "danger")
            return redirect(url_for("main.bordereau"))
        session["payload"] = build_json_payload(extracted, numero, year)
        return redirect(url_for("main.preview"))

    return render_template(
        "bordereau.html",
        extracted=extracted,
        year_hint=extracted.get("year_hint"),
    )


@bp.route("/preview")
def preview():
    payload = session.get("payload")
    if not payload:
        flash("Renseignez les informations du bordereau.", "warning")
        return redirect(url_for("main.bordereau"))
    rules = load_rules(db_path())
    validated = validate_records(payload["records"], rules)
    session["validated"] = validated
    return render_template("preview.html", payload=payload, records=validated)


@bp.route("/configuration", methods=["GET", "POST"])
def configuration():
    error_types = get_available_error_types()
    error_type_codes = [item["code"] for item in error_types]
    if request.method == "POST":
        correspondences = []
        try:
            correspondences = parse_correspondences(request.form)
            for correspondence in correspondences:
                if correspondence["error_type"] is None:
                    raise ValueError(
                        "Sélectionnez le type d'erreur JSON de chaque correspondance."
                    )
                if str(correspondence["error_type"]) not in error_type_codes:
                    raise ValueError(
                        f"Le code erreur {correspondence['error_type']} n'est pas présent "
                        "dans les données JSON disponibles."
                    )
                for table in correspondence["tables"]:
                    validate_oracle_identifier_fields(table)
        except ValueError as error:
            flash(str(error), "danger")
            return render_template(
                "configuration.html",
                correspondences=correspondences,
                error_types=error_types,
                error_type_codes=error_type_codes,
            ), 400
        save_oracle_correspondences(correspondences)
        flash("Configuration métier enregistrée.", "success")
        return redirect(url_for("main.configuration"))

    correspondences = get_oracle_correspondences()
    return render_template(
        "configuration.html",
        correspondences=correspondences,
        error_types=error_types,
        error_type_codes=error_type_codes,
    )


@bp.route("/validation")
def validation():
    payload = session.get("payload")
    validated = session.get("validated")
    if not payload or validated is None:
        flash("Effectuez d'abord l'aperçu des données.", "warning")
        return redirect(url_for("main.preview"))
    valid = sum(1 for row in validated if row["status"] in ("VALID", "WARNING"))
    invalid = sum(1 for row in validated if row["status"] == "ERROR")
    return render_template(
        "validation.html",
        payload=payload,
        records=validated,
        valid=valid,
        invalid=invalid,
    )


@bp.route("/generate", methods=["POST"])
def generate():
    payload = session.get("payload")
    validated = session.get("validated")
    if not payload or validated is None:
        flash("Aucune donnée valide à générer.", "danger")
        return redirect(url_for("main.upload"))

    try:
        rules = load_rules(db_path())
        statements, rejected = generate_sql(
            payload,
            validated,
            rules,
            get_oracle_correspondences(),
        )
        if not statements:
            flash("Aucune instruction SQL générée. Vérifiez la configuration métier.", "warning")
            return redirect(url_for("main.validation"))
        document = build_sql_document(payload, statements)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("main.validation"))

    valid_count = sum(
        1 for row in validated
        if row["status"] in ("VALID", "WARNING")
    )
    filename = (
        f"update_bordereau_{payload['metadata']['numero_bordereau']}_"
        f"{payload['metadata']['annee']}.sql"
    )
    sql_path = current_app.config["SQL_FOLDER"] / filename
    sql_path.write_text(document, encoding="utf-8")

    with get_connection(db_path()) as connection:
        connection.execute(
            """
            INSERT INTO processing_history
            (source_file, sheet_name, numero_bordereau, annee,
             total_records, valid_records, invalid_records, sql_filename, sql_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["metadata"]["source_file"],
                payload["metadata"]["sheet"],
                payload["metadata"]["numero_bordereau"],
                payload["metadata"]["annee"],
                payload["metadata"]["total_records"],
                valid_count,
                len(rejected),
                filename,
                len(statements),
            ),
        )

    session["sql_document"] = document
    session["sql_filename"] = filename
    session["sql_count"] = len(statements)
    return redirect(url_for("main.results"))


@bp.route("/results")
def results():
    payload = session.get("payload")
    if not payload:
        flash("Aucun traitement disponible.", "warning")
        return redirect(url_for("main.dashboard"))
    with get_connection(db_path()) as connection:
        history = connection.execute(
            "SELECT * FROM processing_history ORDER BY id DESC"
        ).fetchall()
    return render_template(
        "results.html",
        payload=payload,
        filename=session.get("sql_filename"),
        sql_count=session.get("sql_count", 0),
        history=history,
    )


@bp.route("/download")
def download():
    filename = session.get("sql_filename")
    document = session.get("sql_document")
    if not filename or document is None:
        flash("Aucun fichier SQL à télécharger.", "warning")
        return redirect(url_for("main.results"))
    return send_file(
        BytesIO(document.encode("utf-8")),
        mimetype="application/sql",
        as_attachment=True,
        download_name=filename,
    )
