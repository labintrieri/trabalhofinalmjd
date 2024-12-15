from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
from urllib.parse import quote
import json
import time

app = Flask(__name__)

# Keep all your existing code but change the bottom part to:

# Remove this
# if __name__ == "__main__":
#     app.run(debug=True)
# app = app

# Add this instead:
if __name__ == "__main__":
    app.run() 