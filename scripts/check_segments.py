from app import app
from models import db, Segment, SegmentContact, Contact

with app.app_context():
    segs = Segment.query.all()
    print('Segments:', len(segs))
    for s in segs:
        count = SegmentContact.query.filter_by(segment_id=s.id).count()
        print(s.id, s.name, 'members_count_via_relation=', count, 'filter_conditions=', s.filter_conditions)
    # list first 10 contacts
    cs = Contact.query.limit(10).all()
    print('Contacts sample:', [(c.id,c.email,c.company) for c in cs])
