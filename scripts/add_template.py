#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script to add the phone promotion email template to the database
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Template

def add_template():
    """Add the phone promotion template to the database"""
    with app.app_context():
        # Check if template already exists
        existing = Template.query.filter_by(name='Thế Giới Di Động - Khuyến Mãi').first()
        if existing:
            print("✓ Template already exists in database")
            return

        # Read the template HTML file
        template_path = os.path.join(os.path.dirname(__file__), 'static', 'templates', 'phone_promotion_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Create new template
        template = Template(
            name='Thế Giới Di Động - Khuyến Mãi',
            description='Mẫu email khuyến mãi điện thoại cao cấp với thiết kế gradient, sản phẩm nổi bật, ưu đãi đặc biệt và mobile responsive',
            html_content=html_content
        )

        try:
            db.session.add(template)
            db.session.commit()
            print("✓ Template added successfully to database!")
            print(f"  Name: {template.name}")
            print(f"  Description: {template.description}")
            print(f"  Created at: {template.created_at}")
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error adding template: {e}")
            sys.exit(1)

if __name__ == '__main__':
    add_template()
