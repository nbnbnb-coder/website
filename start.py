import os
import threading
from flask import Flask
import socket as s
from server import *

app = Flask(__name__)

HOST = s.gethostbyname(s.gethostname())

@app.route("/")
def home():
    return "Bot is running on Render!/n server ip : " + HOST

def start(host, port):
    main(host, port)

if __name__ == "__main__":
    threading.Thread(target=lambda :start(HOST, port), daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host=HOST, port=port)
