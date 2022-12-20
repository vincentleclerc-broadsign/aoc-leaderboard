from app import app, start_logging

if __name__ == "__main__":
    start_logging()
    app.run(host="0.0.0.0", port=10000)
