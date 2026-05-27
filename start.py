import os
import threading
from flask import Flask
import socket as s

app = Flask(__name__)

HOST = s.gethostbyname(s.gethostname())

@app.route("/")
def home():
    return "Bot is running on Render!/n server ip : " + HOST

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host=HOST, port=port)
