from flask import Flask

from config import Config
from routes.api import api
from routes.pages import pages
from routes.staff_api import staff_api
from routes.analytics_api import analytics_api


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.sort_keys = False
    app.register_blueprint(pages)
    app.register_blueprint(api)
    app.register_blueprint(staff_api)
    app.register_blueprint(analytics_api)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)