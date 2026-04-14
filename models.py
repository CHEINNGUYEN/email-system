from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Modèle pour les utilisateurs du système"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='employee')  # admin, employee
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    campaigns = db.relationship('Campaign', backref='creator', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'


class Contact(db.Model):
    """Modèle pour les contacts/destinataires"""
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    company = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    custom_fields = db.Column(db.JSON)  # Champs personnalisés
    subscribed = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_opened = db.Column(db.DateTime)
    last_clicked = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    owner = db.relationship('User', backref=db.backref('my_contacts', lazy=True))
    # Relations
    segments = db.relationship('SegmentContact', back_populates='contact')


class Segment(db.Model):
    """Modèle pour les segments de contacts"""
    __tablename__ = 'segments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    filter_conditions = db.Column(db.JSON)  # Conditions de filtrage
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Relations
    contacts = db.relationship('SegmentContact', back_populates='segment')


class SegmentContact(db.Model):
    """Table de liaison entre segments et contacts"""
    __tablename__ = 'segment_contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    segment_id = db.Column(db.Integer, db.ForeignKey('segments.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    segment = db.relationship('Segment', back_populates='contacts')
    contact = db.relationship('Contact', back_populates='segments')


class Campaign(db.Model):
    """Modèle pour les campagnes d'email"""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    sender_name = db.Column(db.String(100))
    sender_email = db.Column(db.String(120))
    html_content = db.Column(db.Text)
    text_content = db.Column(db.Text)
    
    status = db.Column(db.String(20), default='draft')  # draft, scheduled, sending, sent
    scheduled_time = db.Column(db.DateTime)
    sent_time = db.Column(db.DateTime)
    
    # Destinataires
    send_to_all = db.Column(db.Boolean, default=False)
    segment_id = db.Column(db.Integer, db.ForeignKey('segments.id'))
    
    # Statistiques
    total_sent = db.Column(db.Integer, default=0)
    total_delivered = db.Column(db.Integer, default=0)
    total_bounced = db.Column(db.Integer, default=0)
    total_unsubscribed = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relations
    segment = db.relationship('Segment', backref='campaigns')
    logs = db.relationship('EmailLog', backref='campaign', lazy=True)

    def get_recipients(self):
        """
        Lấy danh sách các liên hệ (Contact) sẽ nhận email của chiến dịch này.
        Dựa trên cấu hình: Gửi tất cả hoặc Gửi theo phân đoạn (Segment).
        """
        if self.send_to_all:
            # Gửi cho tất cả liên hệ đã đăng ký của chủ sở hữu chiến dịch
            return Contact.query.filter_by(user_id=self.user_id, subscribed=True).all()
        elif self.segment:
            # Gửi cho các thành viên trong phân đoạn (chỉ những người còn đăng ký)
            return [sc.contact for sc in self.segment.contacts if sc.contact and sc.contact.subscribed]
        return []


class Automation(db.Model):
    """Modèle pour les workflows d'automation"""
    __tablename__ = 'automations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    trigger_type = db.Column(db.String(50))  # contact_added, email_opened, etc.
    trigger_config = db.Column(db.JSON)
    workflow_steps = db.Column(db.JSON)  # Liste des étapes
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Relations
    executions = db.relationship('AutomationExecution', backref='automation', lazy=True)


class AutomationExecution(db.Model):
    """Suivi des exécutions d'automation"""
    __tablename__ = 'automation_executions'
    
    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.Integer, db.ForeignKey('automations.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False)
    current_step = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='running')  # running, completed, failed
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relations
    contact = db.relationship('Contact', backref='automation_executions')


class EmailLog(db.Model):
    """Log des emails envoyés"""
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id', ondelete='CASCADE'), nullable=False)
    
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered = db.Column(db.Boolean, default=False)
    opened = db.Column(db.Boolean, default=False)
    clicked = db.Column(db.Boolean, default=False)
    bounced = db.Column(db.Boolean, default=False)
    
    opened_at = db.Column(db.DateTime)
    clicked_at = db.Column(db.DateTime)
    
    error_message = db.Column(db.Text)
    
    # Relations
    contact = db.relationship('Contact', backref='email_logs')


class Template(db.Model):
    """Modèle pour les templates d'email"""
    __tablename__ = 'templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    html_content = db.Column(db.Text)
    thumbnail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
