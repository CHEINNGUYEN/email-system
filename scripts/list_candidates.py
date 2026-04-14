from app import app
from models import Contact

patterns = ["%example.com", "import%", "test-recipient%", 'alice@example.com','bob@example.com','charlie@example.com','diana@example.com']

with app.app_context():
    q = Contact.query.filter(
        (Contact.email.ilike(patterns[0])) |
        (Contact.email.ilike(patterns[1])) |
        (Contact.email.ilike(patterns[2])) |
        (Contact.email.in_([patterns[3], patterns[4], patterns[5], patterns[6]]))
    ).order_by(Contact.created_at.asc())
    candidates = q.all()
    print(f'Found {len(candidates)} candidate(s):')
    for c in candidates:
        print(f'{c.id}\t{c.email}\t{(c.first_name or "")} {(c.last_name or "")}\tcreated_at={c.created_at}')
