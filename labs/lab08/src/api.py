from flask import Flask
from flask_restx import Api, Resource

app = Flask(__name__)
api = Api(
    app,
    version="1.0",
    title="Smart Wastebin API",
    description="REST API for querying Smart Wastebin sensor data and bin status",
)

ns = api.namespace("bins", description="Wastebin operations")


@ns.route("/")
class BinList(Resource):
    def get(self):
        """List all registered bins."""
        return {"bins": []}, 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)