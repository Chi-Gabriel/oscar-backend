# File: kapricorn/__init__.py

import os
from flask import Flask
import logging

def create_app(config_class='kapricorn.config.Config'):
    """Creates and configures the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration from config.py
    app.config.from_object(config_class)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # Already exists

    # Setup logging
    logging.basicConfig(level=logging.DEBUG if app.debug else logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
    app.logger.info('Kapricorn Backend starting up...')

    # Register Blueprints
    from .routes import chat_bp
    app.register_blueprint(chat_bp)
    
    from .routes.recommendation_routes import recommend_bp
    app.register_blueprint(recommend_bp)

    # Add other initializations here (like database, mail, etc. if needed later)
    # For now, we only need the chat blueprint.

    app.logger.info('Application setup complete.')
    return app