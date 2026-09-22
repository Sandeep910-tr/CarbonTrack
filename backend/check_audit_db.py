from models.db import db, AuditLog
from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    count = AuditLog.query.count()
    print(f"Total AuditLog entries: {count}")
    if count > 0:
        first = AuditLog.query.first()
        print(f"Example entry: {first.to_dict()}")
