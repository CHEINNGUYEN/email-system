import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from models import db, EmailLog
from jinja2 import Template
from bs4 import BeautifulSoup
import urllib.parse

class EmailService:
    """
    Dịch vụ xử lý gửi Email qua giao thức SMTP hoặc các API bên thứ ba.
    Hỗ trợ cá nhân hóa nội dung và theo dõi chiến dịch.
    """
    
    def __init__(self):
        # Cấu hình SMTP
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        
        # Cấu hình Mailchimp (Tùy chọn)
        self.mailchimp_api_key = os.getenv('MAILCHIMP_API_KEY', '')
        self.mailchimp_server = os.getenv('MAILCHIMP_SERVER_PREFIX', 'us1')
    
    def personalize_content(self, content, contact):
        """
        Thay thế các tag cá nhân hóa (như {{first_name}}) bằng dữ liệu thực của liên hệ.
        """
        template = Template(content)
        
        context = {
            'first_name': contact.first_name or '',
            'last_name': contact.last_name or '',
            'full_name': f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
            'email': contact.email,
            'company': contact.company or '',
            'phone': contact.phone or ''
        }
        
        # Thêm các trường tùy chỉnh nếu có
        if contact.custom_fields:
            context.update(contact.custom_fields)
        
        return template.render(**context)
    
    def send_email_smtp(self, recipient_email, subject, html_content, sender_name=None, sender_email=None):
        """
        Gửi một email đơn lẻ thông qua máy chủ SMTP.
        Trả về: (Trạng thái thành công, Thông báo lỗi nếu có)
        """
        try:
            # Khởi tạo đối tượng email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_name} <{sender_email}>" if sender_name else sender_email or self.smtp_username
            msg['To'] = recipient_email
            
            # Đính kèm nội dung HTML
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Thực hiện kết nối và gửi
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            return True, None
        
        except Exception as e:
            return False, str(e)
    
    def send_campaign(self, campaign, recipients, base_url=None):
        """
        Xử lý gửi email hàng loạt cho một chiến dịch.
        Bao gồm việc tạo nhật ký gửi (log) và chèn link Unsubscribe.
        """
        from flask import request
        success_count = 0
        
        for contact in recipients:
            # 1. Cá nhân hóa nội dung và tiêu đề
            personalized_content = self.personalize_content(campaign.html_content, contact)
            personalized_subject = self.personalize_content(campaign.subject, contact)
            
            # 2. Tạo bản ghi nhật ký gửi thư
            log = EmailLog(
                campaign_id=campaign.id,
                contact_id=contact.id,
                sent_at=datetime.now(),
                delivered=False
            )
            db.session.add(log)
            db.session.flush() # Để lấy log.id
            
            # 3. Chèn liên kết Hủy đăng ký (Unsubscribe) - Bắt buộc cho email marketing
            effective_url = base_url if base_url else "http://localhost:5000"
            unsubscribe_url = f"{effective_url.rstrip('/')}/unsubscribe/{contact.id}"
            unsubscribe_tag = f"""
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #64748b;">
                <p>Bạn nhận được email này vì đã đăng ký bản tin từ chúng tôi.</p>
                <p>
                    <a href="{unsubscribe_url}" style="color: #4f46e5; text-decoration: underline;">Hủy đăng ký (Unsubscribe)</a>
                </p>
            </div>
            """
            
            # Chèn link vào cuối thẻ body hoặc cuối nội dung
            if '</body>' in personalized_content:
                personalized_content = personalized_content.replace('</body>', f'{unsubscribe_tag}</body>')
            else:
                personalized_content += unsubscribe_tag
            
            # 4. Thực hiện gửi qua SMTP
            success, error = self.send_email_smtp(
                recipient_email=contact.email,
                subject=personalized_subject,
                html_content=personalized_content,
                sender_name=campaign.sender_name,
                sender_email=campaign.sender_email
            )
            
            # 5. Cập nhật nhật ký kết quả
            log.delivered = success
            log.error_message = error
            
            if success:
                success_count += 1
        
        # Lưu tất cả các thay đổi nhật ký vào DB
        db.session.commit()
        return success_count
    
    def send_mailchimp_campaign(self, campaign, recipients):
        """
        (Tùy chọn) Gửi chiến dịch qua API của Mailchimp nếu được cấu hình.
        """
        if not self.mailchimp_api_key:
            return 0
        
        try:
            import mailchimp_marketing as MailchimpMarketing
            client = MailchimpMarketing.Client()
            client.set_config({
                "api_key": self.mailchimp_api_key,
                "server": self.mailchimp_server
            })
            # Logic Mailchimp sẽ được bổ sung khi có nhu cầu cụ thể
            return len(recipients)
        except Exception as e:
            print(f"Lỗi Mailchimp: {e}")
            return 0
    
