from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Secure Student Document Management System</h1><p>Phase 1 running successfully.</p>"

if __name__ == "__main__":
    app.run(debug=True)
