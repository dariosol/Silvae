#!/usr/bin/env python3
"""
Reset or create the superuser admin account.
Run this script once to set admin / password for testing:
    python create_admin.py
"""
from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.set_password('password')
        db.session.commit()
        print("Admin password reset to 'password'")
    else:
        admin = User(username='admin', role='superuser', city=None)
        admin.set_password('password')
        db.session.add(admin)
        db.session.commit()
        print("Admin created with username='admin' password='password'")
