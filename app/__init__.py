
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config
import os

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize the database
    db.init_app(app)

    # Import models
    from app import models

    # Register routes
    from app.routes import main
    app.register_blueprint(main)

    # Create database tables
    with app.app_context():
        db.create_all()

    return app
