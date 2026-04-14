import os
import pickle
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import google.generativeai as genai

# Local imports
from models import db, User, Contact, Segment, SegmentContact, Campaign, Automation, EmailLog, Template, AutomationExecution
from email_service import EmailService

# ── CẤU HÌNH HỆ THỐNG ──────────────────────────────────────────────────

load_dotenv(override=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///email_system.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Khởi tạo các dịch vụ
db.init_app(app)
email_service = EmailService()

# ── SCHEDULER (GỬI EMAIL TỰ ĐỘNG) ──────────────────────────────────────

def check_scheduled_campaigns():
    """Hàm chạy ngầm kiểm tra và gửi các chiến dịch đã đến hẹn."""
    with app.app_context():
        now = datetime.now()
        due_campaigns = Campaign.query.filter(
            Campaign.status == 'scheduled',
            Campaign.scheduled_time <= now
        ).all()
        
        for campaign in due_campaigns:
            recipients = campaign.get_recipients()
            
            if recipients:
                campaign.status = 'sending'
                campaign.total_sent = len(recipients)
                db.session.commit()
                
                # Gửi email qua EmailService
                base_url = os.getenv('BASE_URL')
                success_count = email_service.send_campaign(campaign, recipients, base_url=base_url)
                
                campaign.total_delivered = success_count
                campaign.sent_time = datetime.now()
                campaign.status = 'sent' if success_count > 0 else 'failed'
            else:
                campaign.status = 'failed'
            
            db.session.commit()

# Khởi tạo và bắt đầu Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_scheduled_campaigns, trigger="interval", minutes=1)
scheduler.start()

# ── QUẢN LÝ ĐĂNG NHẬP (AUTH) ──────────────────────────────────────────

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    # Sử dụng Session.get thay cho Query.get vì cái sau đã bị deprecated
    return db.session.get(User, int(user_id))

# ── TÀI NGUYÊN TĨNH (ASSETS) ──────────────────────────────────────────

@app.route('/logo.png')
@app.route('/<path:subpath>/logo.png')
def serve_logo(subpath=None):
    """Phục vụ logo từ thư mục static cho mọi đường dẫn (tránh lỗi 404)."""
    return send_from_directory(app.static_folder, 'logo.png')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# ── ROUTES CHÍNH (MAIN ROUTES) ───────────────────────────────────────

@app.route('/unsubscribe/<int:contact_id>')
def unsubscribe(contact_id):
    """Xử lý yêu cầu hủy đăng ký từ người dùng"""
    contact = db.session.get(Contact, contact_id)
    if contact:
        contact.subscribed = False
        db.session.commit()
    return render_template('unsubscribe.html', contact=contact)

@app.route('/')
def index():
    """Trường hợp gốc: Chuyển hướng nếu đã đăng nhập hoặc yêu cầu đăng nhập."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ── XÁC THỰC NGƯỜI DÙNG (AUTHENTICATION) ──────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Xử lý đăng ký tài khoản mới."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Tên người dùng đã tồn tại', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email đã tồn tại', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, role='employee')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Đăng ký thành công! Bạn có thể đăng nhập ngay bây giờ.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Xử lý đăng nhập người dùng."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Đăng nhập thành công!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('Tên người dùng hoặc mật khẩu không đúng', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Đăng xuất người dùng."""
    logout_user()
    flash('Đã đăng xuất', 'info')
    return redirect(url_for('login'))

# ── BẢNG ĐIỀU KHIỂN (DASHBOARD) ───────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    """Hiển thị tổng quan số liệu thống kê."""
    if current_user.is_admin():
        total_contacts = Contact.query.filter_by(subscribed=True).count()
        total_campaigns = Campaign.query.count()
        total_automations = Automation.query.filter_by(active=True).count()
        recent_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).limit(5).all()
        total_sent = db.session.query(db.func.sum(Campaign.total_sent)).scalar() or 0
    else:
        total_contacts = Contact.query.filter_by(user_id=current_user.id, subscribed=True).count()
        total_campaigns = Campaign.query.filter_by(user_id=current_user.id).count()
        total_automations = Automation.query.filter_by(user_id=current_user.id, active=True).count()
        recent_campaigns = Campaign.query.filter_by(user_id=current_user.id).order_by(
            Campaign.created_at.desc()
        ).limit(5).all()
        total_sent = db.session.query(db.func.sum(Campaign.total_sent)).filter(Campaign.user_id == current_user.id).scalar() or 0
    
    # Số liệu tracking mặc định là 0 (Đã gỡ hệ thống Tracking)
    total_opened = 0
    total_clicked = 0
    
    from datetime import timedelta
    growth_labels, growth_data = [], []
    today = datetime.now().date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        growth_labels.append(day.strftime('%d/%m'))
        if current_user.is_admin():
            count = Contact.query.filter(db.func.date(Contact.created_at) <= day).count()
        else:
            count = Contact.query.filter(Contact.user_id == current_user.id, db.func.date(Contact.created_at) <= day).count()
        growth_data.append(count)

    return render_template('dashboard.html',
                           total_contacts=total_contacts,
                           total_campaigns=total_campaigns,
                           total_automations=total_automations,
                           total_opened=total_opened,
                           total_clicked=total_clicked,
                           total_sent=total_sent,
                           growth_labels=growth_labels,
                           growth_data=growth_data,
                           recent_campaigns=recent_campaigns)

# ── QUẢN LÝ LIÊN HỆ (CONTACTS) ───────────────────────────────────────

@app.route('/contacts')
@login_required
def contacts():
    """Xem danh sách liên hệ theo phân trang."""
    page = request.args.get('page', 1, type=int)
    if current_user.is_admin():
        query = Contact.query
    else:
        query = Contact.query.filter_by(user_id=current_user.id)
    
    contacts_pagination = query.order_by(Contact.id.desc()).paginate(page=page, per_page=20)
    return render_template('contacts.html', contacts=contacts_pagination)

@app.route('/contacts/add', methods=['GET', 'POST'])
@login_required
def add_contact():
    """Thêm liên hệ mới thủ công."""
    if request.method == 'POST':
        email = request.form.get('email')
        if Contact.query.filter_by(user_id=current_user.id, email=email).first():
            flash('Liên hệ này đã tồn tại', 'warning')
            return redirect(url_for('contacts'))
        
        contact = Contact(
            email=email,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            company=request.form.get('company'),
            phone=request.form.get('phone'),
            user_id=current_user.id
        )
        db.session.add(contact)
        db.session.commit()
        flash('Thêm liên hệ thành công', 'success')
        return redirect(url_for('contacts'))
    
    return render_template('add_contact.html')

@app.route('/contacts/import', methods=['GET', 'POST'])
@login_required
def import_contacts():
    """Nhập liên hệ từ file CSV hoặc XLSX."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Không có tệp được chọn', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Không có tệp được chọn', 'danger')
            return redirect(request.url)
        
        if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            try:
                import pandas as pd
                import io
                file_stream = io.BytesIO(file.read())
                
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file_stream)
                else:
                    df = pd.read_excel(file_stream)
                
                df.columns = [str(col).lower().strip() for col in df.columns]
                imported, skipped = 0, 0
                
                for idx, row in df.iterrows():
                    try:
                        email = str(row.get('email', '')).strip()
                        if not email or email.lower() == 'nan' or '@' not in email:
                            skipped += 1
                            continue
                        
                        if Contact.query.filter_by(user_id=current_user.id, email=email).first():
                            skipped += 1
                            continue
                        
                        contact = Contact(
                            email=email,
                            first_name=str(row.get('first_name', '')).strip().replace('nan', ''),
                            last_name=str(row.get('last_name', '')).strip().replace('nan', ''),
                            company=str(row.get('company', '')).strip().replace('nan', ''),
                            phone=str(row.get('phone', '')).strip().replace('nan', ''),
                            user_id=current_user.id
                        )
                        db.session.add(contact)
                        imported += 1
                    except Exception:
                        skipped += 1
                        continue
                
                db.session.commit()
                flash(f'Đã nhập thành công {imported} liên hệ, bỏ qua {skipped} dòng.', 'success')
                return redirect(url_for('contacts'))
            except Exception as e:
                db.session.rollback()
                flash(f'Lỗi khi xử lý tệp: {str(e)}', 'danger')
        else:
            flash('Định dạng tệp không hỗ trợ', 'danger')
    
    return render_template('import_contacts.html')

@app.route('/contacts/<int:contact_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contact(contact_id):
    """Sửa thông tin liên hệ."""
    contact = Contact.query.filter_by(id=contact_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        contact.email = request.form.get('email')
        contact.first_name = request.form.get('first_name')
        contact.last_name = request.form.get('last_name')
        contact.company = request.form.get('company')
        contact.phone = request.form.get('phone')
        db.session.commit()
        flash('Cập nhật liên hệ thành công', 'success')
        return redirect(url_for('contacts'))
    return render_template('edit_contact.html', contact=contact)

@app.route('/contacts/<int:contact_id>/delete', methods=['POST'])
@login_required
def delete_contact(contact_id):
    """Xóa liên hệ và các bản ghi liên quan."""
    if current_user.is_admin():
        contact = db.session.get(Contact, contact_id)
    else:
        contact = Contact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    
    if not contact:
        flash('Không tìm thấy liên hệ', 'danger')
        return redirect(url_for('contacts'))

    try:
        EmailLog.query.filter_by(contact_id=contact_id).delete()
        SegmentContact.query.filter_by(contact_id=contact_id).delete()
        db.session.delete(contact)
        db.session.commit()
        flash('Đã xóa liên hệ thành công', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Lỗi khi xóa: {str(e)}', 'danger')
    
    return redirect(url_for('contacts'))

# ── PHÂN ĐOẠN LIÊN HỆ (SEGMENTS) ──────────────────────────────────────

@app.route('/segments')
@login_required
def segments():
    """Xem danh sách phân đoạn và thống kê thành viên."""
    segments = Segment.query.filter_by(user_id=current_user.id).all()
    user_contacts = Contact.query.filter_by(user_id=current_user.id).all()
    
    def contact_matches(contact, cond):
        field, op, val = cond.get('field'), cond.get('operator'), cond.get('value', '')
        left = str(getattr(contact, field, '') or '')
        if op == 'equals': return left == val
        if op == 'not_equals': return left != val
        if op == 'contains': return val.lower() in left.lower()
        return False

    segments_info = []
    for seg in segments:
        count, sample = 0, []
        if seg.filter_conditions:
            for c in user_contacts:
                if all(contact_matches(c, cond) for cond in seg.filter_conditions):
                    count += 1
                    if len(sample) < 5: sample.append(c.email)
        else:
            count = len(seg.contacts)
        segments_info.append({'segment': seg, 'count': count, 'sample': sample})
    
    return render_template('segments.html', segments_info=segments_info)

@app.route('/segments/create', methods=['GET', 'POST'])
@login_required
def create_segment():
    """Tạo phân đoạn mới với điều kiện lọc."""
    if request.method == 'POST':
        segment = Segment(
            name=request.form.get('name'),
            description=request.form.get('description'),
            user_id=current_user.id
        )
        fields = request.form.getlist('field[]')
        ops = request.form.getlist('operator[]')
        vals = request.form.getlist('value[]')
        conditions = [{'field': f, 'operator': o, 'value': v} for f, o, v in zip(fields, ops, vals) if f]
        segment.filter_conditions = conditions
        
        db.session.add(segment)
        db.session.commit()
        flash('Tạo phân đoạn thành công', 'success')
        return redirect(url_for('segments'))
    
    return render_template('create_segment.html')

@app.route('/segments/<int:segment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_segment(segment_id):
    """Cập nhật thông tin và điều kiện phân đoạn."""
    segment = Segment.query.filter_by(id=segment_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        segment.name = request.form.get('name')
        segment.description = request.form.get('description')
        fields = request.form.getlist('field[]')
        ops = request.form.getlist('operator[]')
        vals = request.form.getlist('value[]')
        segment.filter_conditions = [{'field': f, 'operator': o, 'value': v} for f, o, v in zip(fields, ops, vals) if f]
        db.session.commit()
        flash('Cập nhật phân đoạn thành công', 'success')
        return redirect(url_for('segments'))
    return render_template('create_segment.html', segment=segment)

@app.route('/segments/<int:segment_id>/delete', methods=['POST'])
@login_required
def delete_segment(segment_id):
    """Xóa phân đoạn."""
    segment = Segment.query.filter_by(id=segment_id, user_id=current_user.id).first_or_404()
    SegmentContact.query.filter_by(segment_id=segment_id).delete()
    Campaign.query.filter_by(segment_id=segment_id).update({Campaign.segment_id: None})
    db.session.delete(segment)
    db.session.commit()
    flash('Đã xóa phân đoạn', 'success')
    return redirect(url_for('segments'))

# ── CÔNG CỤ AI & PHÂN TÍCH (AI TOOLS) ────────────────────────────────

@app.route('/check-spam')
def checkcontent():
    """Trang giao diện kiểm tra Spam."""
    return render_template('check_spam.html')

@app.route('/predict', methods=['POST'])
def predict():
    """Dự đoán Spam bằng mô hình Machine Learning."""
    try:
        data = request.get_json()
        email_content = data.get('email')
        model_code = data.get('algorithm', 'RF')
        
        from ml_pipeline import CustomFeatures, TextCleaner
        model_path = os.path.join(app.root_path, 'models', f'model_{model_code}.pkl')
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        prediction = model.predict([email_content])[0]
        return jsonify({
            'prediction': 'spam' if prediction == 1 else 'ham',
            'algorithm': model_code
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/segments/<int:segment_id>/members', methods=['GET', 'POST'])
@login_required
def segment_members(segment_id):
    """Quản lý thành viên trong một phân đoạn."""
    segment = Segment.query.get_or_404(segment_id)
    if segment.user_id != current_user.id and not current_user.is_admin():
        flash('Không có quyền truy cập', 'danger')
        return redirect(url_for('segments'))

    members = [sc.contact for sc in segment.contacts if sc.contact]
    if request.method == 'POST':
        email = request.form.get('email')
        contact = Contact.query.filter_by(email=email).first()
        if not contact:
            contact = Contact(email=email, user_id=current_user.id)
            db.session.add(contact)
            db.session.commit()
        
        if not SegmentContact.query.filter_by(segment_id=segment_id, contact_id=contact.id).first():
            sc = SegmentContact(segment_id=segment_id, contact_id=contact.id)
            db.session.add(sc)
            db.session.commit()
            flash('Đã thêm thành viên', 'success')
        return redirect(url_for('segment_members', segment_id=segment_id))
    
    return render_template('segment_members.html', segment=segment, members=members)

@app.route('/segments/<int:segment_id>/members/remove', methods=['POST'])
@login_required
def remove_segment_member(segment_id):
    """Xóa thành viên khỏi phân đoạn."""
    contact_id = request.form.get('contact_id')
    sc = SegmentContact.query.filter_by(segment_id=segment_id, contact_id=contact_id).first()
    if sc:
        db.session.delete(sc)
        db.session.commit()
    return redirect(url_for('segment_members', segment_id=segment_id))

# ── QUẢN LÝ CHIẾN DỊCH (CAMPAIGN MANAGEMENT) ──────────────────────────

@app.route('/campaigns')
@login_required
def campaigns():
    """Danh sách chiến dịch."""
    campaigns = Campaign.query.filter_by(user_id=current_user.id).order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns.html', campaigns=campaigns)

@app.route('/campaigns/create', methods=['GET', 'POST'])
@login_required
def create_campaign():
    """Tạo mới hoặc lên lịch chiến dịch."""
    if request.method == 'POST':
        campaign = Campaign(
            name=request.form.get('name'),
            subject=request.form.get('subject'),
            sender_name=request.form.get('sender_name'),
            sender_email=request.form.get('sender_email'),
            html_content=request.form.get('html_content'),
            user_id=current_user.id
        )
        send_to = request.form.get('send_to')
        if send_to == 'all': campaign.send_to_all = True
        else: campaign.segment_id = int(send_to)
        
        if request.form.get('schedule') == 'later':
            scheduled_time = request.form.get('scheduled_time')
            if scheduled_time:
                campaign.scheduled_time = datetime.strptime(scheduled_time, '%Y-%m-%dT%H:%M')
                campaign.status = 'scheduled'
        
        db.session.add(campaign)
        db.session.commit()
        flash('Thành công', 'success')
        return redirect(url_for('campaigns'))
    
    segments = Segment.query.filter_by(user_id=current_user.id).all()
    return render_template('create_campaign.html', segments=segments)

@app.route('/campaigns/<int:campaign_id>/send', methods=['POST'])
@login_required
def send_campaign(campaign_id):
    """Gửi chiến dịch ngay lập tức."""
    campaign = Campaign.query.get_or_404(campaign_id)
    recipients = campaign.get_recipients()
    if not recipients:
        flash('Không có người nhận', 'warning')
        return redirect(url_for('campaigns'))
    
    campaign.status = 'sending'
    campaign.total_sent = len(recipients)
    db.session.commit()
    
    success_count = email_service.send_campaign(campaign, recipients, base_url=os.getenv('BASE_URL', request.host_url))
    campaign.total_delivered = success_count
    campaign.status = 'sent' if success_count > 0 else 'failed'
    campaign.sent_time = datetime.now()
    db.session.commit()
    
    flash(f'Đã gửi tới {success_count} người nhận', 'success')
    return redirect(url_for('campaign_stats', campaign_id=campaign_id))

@app.route('/campaigns/<int:campaign_id>/stats')
@login_required
def campaign_stats(campaign_id):
    """Thống kê chi tiết chiến dịch."""
    campaign = Campaign.query.get_or_404(campaign_id)
    return render_template('campaign_stats.html', campaign=campaign)

@app.route('/campaigns/<int:campaign_id>/delete', methods=['POST'])
@login_required
def delete_campaign(campaign_id):
    """Xóa chiến dịch."""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first_or_404()
    db.session.delete(campaign)
    db.session.commit()
    return redirect(url_for('campaigns'))

# ── API & TRỢ LÝ AI ───────────────────────────────────────────────────

@app.route('/api/contacts/search')
@login_required
def api_search_contacts():
    """Tìm kiếm liên hệ nhanh."""
    q = request.args.get('q', '')
    contacts = Contact.query.filter(Contact.email.ilike(f'%{q}%')).limit(10).all()
    return jsonify([{'id': c.id, 'email': c.email} for c in contacts])

@app.route('/api/ai/generate', methods=['POST'])
@login_required
def api_ai_generate():
    """Sử dụng Gemini AI để soạn nội dung email."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key: return jsonify({'error': 'Thiếu API Key'}), 400
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = request.json.get('prompt')
    
    try:
        response = model.generate_content(f"Viết email bằng tiếng Việt, trả về JSON {{'subject': '...', 'html': '...'}}. Nội dung: {prompt}")
        text = response.text
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        import json
        return jsonify(json.loads(text))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── QUẢN TRỊ ADMIN ────────────────────────────────────────────────────

@app.route('/admin/users')
@login_required
def admin_users():
    """Danh sách người dùng (Chỉ Admin)."""
    if not current_user.is_admin(): return redirect(url_for('dashboard'))
    return render_template('admin_users.html', users=User.query.all())

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Quản lý tài khoản người dùng."""
    if not current_user.is_admin(): return redirect(url_for('dashboard'))
    user = db.session.get(User, user_id)
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        if request.form.get('password'): user.set_password(request.form.get('password'))
        db.session.commit()
        return redirect(url_for('admin_users'))
    return render_template('edit_user.html', user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Xóa người dùng và toàn bộ dữ liệu liên quan."""
    if not current_user.is_admin() or user_id == current_user.id:
        return redirect(url_for('admin_users'))
    
    user = db.session.get(User, user_id)
    if not user:
        flash('Người dùng không tồn tại', 'danger')
        return redirect(url_for('admin_users'))

    try:
        # 1. Xóa tất cả EmailLog liên quan đến các chiến dịch của người dùng này
        campaign_ids = [c.id for c in Campaign.query.filter_by(user_id=user_id).all()]
        if campaign_ids:
            EmailLog.query.filter(EmailLog.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
        
        # 2. Xóa tất cả Chiến dịch (Campaign)
        Campaign.query.filter_by(user_id=user_id).delete()
        
        # 3. Xóa các Automation và Execution liên quan
        automation_ids = [a.id for a in Automation.query.filter_by(user_id=user_id).all()]
        if automation_ids:
            AutomationExecution.query.filter(AutomationExecution.automation_id.in_(automation_ids)).delete(synchronize_session=False)
        Automation.query.filter_by(user_id=user_id).delete()
        
        # 4. Xóa Segment và SegmentContact (liên kết)
        segment_ids = [s.id for s in Segment.query.filter_by(user_id=user_id).all()]
        if segment_ids:
            SegmentContact.query.filter(SegmentContact.segment_id.in_(segment_ids)).delete(synchronize_session=False)
        Segment.query.filter_by(user_id=user_id).delete()
        
        # 5. Xóa tất cả Liên hệ (Contact)
        Contact.query.filter_by(user_id=user_id).delete()
        
        # 6. Cuối cùng xóa User
        db.session.delete(user)
        db.session.commit()
        flash(f'Đã xóa người dùng {user.username} và toàn bộ dữ liệu liên quan.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Lỗi hệ thống khi xóa người dùng: {str(e)}', 'danger')
        
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, host='0.0.0.0', port=5000)