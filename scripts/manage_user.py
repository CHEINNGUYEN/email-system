import sys
import os
import argparse
from werkzeug.security import generate_password_hash

# Add current directory to path so we can import from local files
sys.path.append(os.getcwd())

from app import app
from models import db, User

def manage_user(username, new_password=None, new_role=None):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"Error: User '{username}' not found.")
            return False
        
        changes = []
        if new_password:
            user.set_password(new_password)
            changes.append("password")
            
        if new_role:
            # Basic validation for roles based on models.py comments
            if new_role not in ['admin', 'employee']:
                print(f"Warning: Role '{new_role}' is not one of the standard roles (admin, employee).")
                confirm = input(f"Do you want to proceed with role '{new_role}' anyway? (y/n): ")
                if confirm.lower() != 'y':
                    print("Role update cancelled.")
                    new_role = None
            
            if new_role:
                user.role = new_role
                changes.append(f"role to '{new_role}'")
        
        if changes:
            db.session.commit()
            print(f"Success: Updated {', '.join(changes)} for user '{username}'.")
        else:
            print("No changes specified.")
            
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage user account (password and role).")
    parser.add_argument("username", help="Username of the account to update")
    parser.add_argument("--password", help="New password for the user")
    parser.add_argument("--role", help="New role for the user (e.g., admin, employee)")

    args = parser.parse_args()

    # If running with positional arguments only (backwards compatibility for the user's previous run)
    # This is a bit tricky with argparse, but I'll make it clear in instructions.
    
    manage_user(args.username, args.password, args.role)

    #python manage_user.py admin --password "MậtKhẩuMới123" --role admin
