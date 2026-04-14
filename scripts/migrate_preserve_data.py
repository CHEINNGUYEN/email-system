#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration script to preserve existing data while adding `user_id` ownership.

Behaviour:
- Back up existing `email_system.db` to `email_system_backup_<ts>.db`.
- Create a new DB `email_system_migrated.db` with the updated schema (models include user_id).
- Copy users from old DB if present; if none, create admin/admin123.
- Copy contacts, segments, campaigns, automations, templates, logs, preserving relations.
- All copied contacts/segments/automations/campaigns will be assigned to an existing user if possible; otherwise assigned to admin.

Note: This script assigns all legacy records to the admin user if no ownership info exists.

Run from project root with venv active:
    .\venv\Scripts\python.exe migrate_preserve_data.py

"""

import os
import shutil
import sqlite3
from datetime import datetime
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_DB = os.path.join(PROJECT_DIR, 'email_system.db')
BACKUP_DB = os.path.join(PROJECT_DIR, f'email_system_backup_{datetime.now().strftime("%Y%m%d%H%M%S")}.db')
NEW_DB_URI = 'sqlite:///email_system_migrated.db'
NEW_DB_FILE = os.path.join(PROJECT_DIR, 'email_system_migrated.db')

print('PROJECT_DIR:', PROJECT_DIR)

if not os.path.exists(OLD_DB):
    print('No existing database found at', OLD_DB)
    sys.exit(1)

# Backup
print('Backing up old database to', BACKUP_DB)
shutil.copy2(OLD_DB, BACKUP_DB)

# Read old data using sqlite3
old_conn = sqlite3.connect(OLD_DB)
old_cur = old_conn.cursor()

def fetch_all(table):
    try:
        old_cur.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in old_cur.description]
        rows = [dict(zip(cols, row)) for row in old_cur.fetchall()]
        return rows
    except Exception as e:
        print(f'Warning: could not read table {table}:', e)
        return []

print('Reading tables from old DB...')
users_old = fetch_all('users')
contacts_old = fetch_all('contacts')
segments_old = fetch_all('segments')
segment_contacts_old = fetch_all('segment_contacts')
campaigns_old = fetch_all('campaigns')
automations_old = fetch_all('automations')
automation_executions_old = fetch_all('automation_executions')
email_logs_old = fetch_all('email_logs')
templates_old = fetch_all('templates')

old_conn.close()

# Initialize app and new DB
print('Initializing application and creating new DB schema...')
from app import app
from models import db, User, Contact, Segment, SegmentContact, Campaign, Automation, AutomationExecution, EmailLog, Template

# Point app to new DB file
app.config['SQLALCHEMY_DATABASE_URI'] = NEW_DB_URI
# Re-init DB bind
db.init_app(app)

with app.app_context():
    # Remove existing migrated file if present
    if os.path.exists(NEW_DB_FILE):
        print('Removing existing', NEW_DB_FILE)
        os.remove(NEW_DB_FILE)

    db.create_all()

    # Helper maps old_id -> new_obj.id
    user_map = {}
    contact_map = {}
    segment_map = {}
    campaign_map = {}
    automation_map = {}

    # 1) Users: copy existing users if any
    print('Migrating users...')
    if users_old:
        for u in users_old:
            # Keep password hash if present
            nu = User(
                username=u.get('username') or f"user_{u.get('id')}",
                email=u.get('email') or f"user{u.get('id')}@example.com",
                role=u.get('role') or 'employee'
            )
            # try to preserve password_hash column if exists
            if 'password_hash' in u and u.get('password_hash'):
                nu.password_hash = u.get('password_hash')
            else:
                nu.set_password('changeme')
            db.session.add(nu)
            db.session.flush()
            user_map[u.get('id')] = nu.id
        db.session.commit()
    else:
        # create admin
        admin = User(username='admin', email='admin@example.com', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        user_map = {}
        # map legacy ownerless data to admin by default; we'll use admin.id as default
        default_admin_id = admin.id
        print('No users found in old DB — created admin:', admin.username)

    # Determine default user id (if old users exist pick first, else admin)
    if users_old:
        # pick the first user in the new DB as default owner
        default_user_id = list(user_map.values())[0]
    else:
        default_user_id = default_admin_id

    print('default_user_id =', default_user_id)

    # 2) Contacts
    print('Migrating contacts...', len(contacts_old))
    for c in contacts_old:
        nc = Contact(
            email=c.get('email') or f"migrated{c.get('id')}@example.com",
            first_name=c.get('first_name'),
            last_name=c.get('last_name'),
            company=c.get('company'),
            phone=c.get('phone'),
            subscribed=bool(c.get('subscribed')) if 'subscribed' in c else True,
            created_at=c.get('created_at') or None,
            last_opened=c.get('last_opened') or None,
            last_clicked=c.get('last_clicked') or None,
            user_id=default_user_id
        )
        db.session.add(nc)
        db.session.flush()
        contact_map[c.get('id')] = nc.id
    db.session.commit()

    # 3) Segments
    print('Migrating segments...', len(segments_old))
    for s in segments_old:
        ns = Segment(
            name=s.get('name') or f"Segment {s.get('id')}",
            description=s.get('description'),
            filter_conditions=s.get('filter_conditions'),
            created_at=s.get('created_at') or None,
            user_id=default_user_id
        )
        db.session.add(ns)
        db.session.flush()
        segment_map[s.get('id')] = ns.id
    db.session.commit()

    # 4) SegmentContact mapping
    print('Migrating segment contacts...', len(segment_contacts_old))
    for sc in segment_contacts_old:
        old_seg_id = sc.get('segment_id')
        old_contact_id = sc.get('contact_id')
        if old_seg_id in segment_map and old_contact_id in contact_map:
            nsc = SegmentContact(segment_id=segment_map[old_seg_id], contact_id=contact_map[old_contact_id], added_at=sc.get('added_at') or None)
            db.session.add(nsc)
    db.session.commit()

    # 5) Campaigns
    print('Migrating campaigns...', len(campaigns_old))
    for cam in campaigns_old:
            nc = Campaign(
            name=cam.get('name') or f"Campaign {cam.get('id')}",
            subject=cam.get('subject'),
            sender_name=cam.get('sender_name'),
            sender_email=cam.get('sender_email'),
            html_content=cam.get('html_content'),
            text_content=cam.get('text_content'),
            status=cam.get('status') or 'draft',
            scheduled_time=cam.get('scheduled_time') or None,
            sent_time=cam.get('sent_time') or None,
            send_to_all=bool(cam.get('send_to_all')) if 'send_to_all' in cam else False,
            segment_id=segment_map.get(cam.get('segment_id')) if cam.get('segment_id') else None,
            total_sent=cam.get('total_sent') or 0,
            total_delivered=cam.get('total_delivered') or 0,
            total_bounced=cam.get('total_bounced') or 0,
            total_unsubscribed=cam.get('total_unsubscribed') or 0,
            created_at=cam.get('created_at') or None,
            user_id=default_user_id
        )
        db.session.add(nc)
        db.session.flush()
        campaign_map[cam.get('id')] = nc.id
    db.session.commit()

    # 6) Automations
    print('Migrating automations...', len(automations_old))
    for a in automations_old:
        na = Automation(
            name=a.get('name') or f"Automation {a.get('id')}",
            description=a.get('description'),
            trigger_type=a.get('trigger_type'),
            trigger_config=a.get('trigger_config'),
            workflow_steps=a.get('workflow_steps'),
            active=bool(a.get('active')) if 'active' in a else True,
            created_at=a.get('created_at') or None,
            user_id=default_user_id
        )
        db.session.add(na)
        db.session.flush()
        automation_map[a.get('id')] = na.id
    db.session.commit()

    # 7) AutomationExecution
    print('Migrating automation executions...', len(automation_executions_old))
    for ae in automation_executions_old:
        old_contact = ae.get('contact_id')
        old_automation = ae.get('automation_id')
        if old_contact in contact_map and old_automation in automation_map:
            nae = AutomationExecution(
                automation_id=automation_map[old_automation],
                contact_id=contact_map[old_contact],
                current_step=ae.get('current_step') or 0,
                status=ae.get('status') or 'running',
                started_at=ae.get('started_at') or None,
                completed_at=ae.get('completed_at') or None
            )
            db.session.add(nae)
    db.session.commit()

    # 8) EmailLogs
    print('Migrating email logs...', len(email_logs_old))
    for el in email_logs_old:
        old_contact = el.get('contact_id')
        old_campaign = el.get('campaign_id')
        if old_contact in contact_map:
            nel = EmailLog(
                campaign_id=campaign_map.get(old_campaign) if old_campaign in campaign_map else None,
                contact_id=contact_map[old_contact],
                sent_at=el.get('sent_at') or None,
                delivered=bool(el.get('delivered')) if 'delivered' in el else False,
                opened=bool(el.get('opened')) if 'opened' in el else False,
                clicked=bool(el.get('clicked')) if 'clicked' in el else False,
                bounced=bool(el.get('bounced')) if 'bounced' in el else False,
                opened_at=el.get('opened_at') or None,
                clicked_at=el.get('clicked_at') or None,
                error_message=el.get('error_message')
            )
            db.session.add(nel)
    db.session.commit()

    # 9) Templates
    print('Migrating templates...', len(templates_old))
    for t in templates_old:
        nt = Template(
            name=t.get('name') or f"Template {t.get('id')}",
            description=t.get('description'),
            html_content=t.get('html_content'),
            thumbnail=t.get('thumbnail'),
            created_at=t.get('created_at') or None
        )
        db.session.add(nt)
    db.session.commit()

print('\nMigration completed successfully.')
print('New DB file:', NEW_DB_FILE)
print('Backup of old DB:', BACKUP_DB)
print('You can replace the old DB with the migrated one by renaming files, or update your app config to use the new DB URI.')
print('\nRecommended next steps:')
print(' - Inspect the new DB file and verify data.')
print(' - If OK, stop the server and replace email_system.db with email_system_migrated.db (keep the backup).')
print('   Example PowerShell commands:')
print('     Stop the app if running;')
print(f"     Rename-Item -Path '{OLD_DB}' -NewName 'email_system_old.db' -ErrorAction Stop; Rename-Item -Path '{NEW_DB_FILE}' -NewName 'email_system.db' -ErrorAction Stop")

