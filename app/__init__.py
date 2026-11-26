from flask import Flask

from config import Config
from app.models.database import init_database
from app.routes.main import bp as main_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
    app.config["SQL_FOLDER"].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE_PATH"].parent.mkdir(parents=True, exist_ok=True)

    init_database(app.config["DATABASE_PATH"])
    app.register_blueprint(main_bp)
    return app
