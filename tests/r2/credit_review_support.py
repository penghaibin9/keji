"""Test helper: mark every synced course as approved, so older credit tests keep checking the totals.

授课学分 now count only after a reviewer approves the course (test_teaching_credit_review.py
exercises that flow through the API). Tests written before the review step call approve_all()
after syncing, which writes the same review record an approval through the API would.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User
from app.reference_data import TeacherCourseTerm,annual_teaching_credits,credit_reviews,credit_review_code,CREDIT_REVIEW_KIND
from app.social_models import SocialResource
from app import reference_data


def assume_approved(monkeypatch):
    """For rule tests on unsaved rows: treat every counted course as approved."""
    monkeypatch.setattr(reference_data,'review_state',lambda review,basis:'approved')


def approve_all(engine):
    with Session(engine) as db:
        rows=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True))).all()
        reviews=credit_reviews(db,[r.id for r in rows]);by_id={r.id:r for r in rows}
        for g in annual_teaching_credits(db,rows):
            for d in g['details']:
                if not d['counted'] or d['review']!='pending':continue
                r=by_id[d['id']];user=db.get(User,r.user_id) if r.user_id else None
                basis={'staff_no':r.staff_no,'origin':r.origin,'course_code':r.course_code,'term_name':r.term_name,'credit':d['credit'],'hours':d['hours']}
                obj=reviews.get(r.id)
                if obj is None:
                    obj=SocialResource(org_id=user.org_id if user else 'school',kind=CREDIT_REVIEW_KIND,code=credit_review_code(r.id),name=r.course_name[:160],state='APPROVED',data={})
                    db.add(obj)
                obj.state='APPROVED';obj.data={'course_term_id':r.id,'staff_no':r.staff_no,'basis':basis,'by':'test','by_name':'测试认定','history':[]}
        db.commit()
