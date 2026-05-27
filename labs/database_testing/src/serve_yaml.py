from flask import Flask, send_file, abort

app = Flask(__name__)

@app.route("/")
def index():
    return send_file("/app/asyncapi.yml", mimetype="text/plain")

@app.route("/<path:anything>")
def block(anything):
    abort(404)   # every other path → 404, nothing exposed

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
