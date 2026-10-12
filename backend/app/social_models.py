"""School social-training extensions; existing masters, accounts and evidence are reused."""
from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, Entity


class SocialProject(Entity, Base):
    __tablename__ = 'social_projects'
    master_id: Mapped[str] = mapped_column(ForeignKey('training_projects.id'), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    cohort: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default='DRAFT')
    data: Mapped[dict] = mapped_column(JSON)
    closeout: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint('master_id', 'cohort'),)


class SocialUnit(Entity, Base):
    __tablename__ = 'social_units'
    project_id: Mapped[str] = mapped_column(ForeignKey('social_projects.id'), index=True)
    external_key: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint('project_id', 'external_key'),)


class SocialPolicy(Entity, Base):
    __tablename__ = 'social_policies'
    period_id: Mapped[str] = mapped_column(ForeignKey('periods.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(32), default='DRAFT')
    data: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer, default=1)


class SocialClaim(Entity, Base):
    __tablename__ = 'social_claims'
    project_id: Mapped[str] = mapped_column(ForeignKey('social_projects.id'), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey('periods.id'), index=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey('social_policies.id'))
    state: Mapped[str] = mapped_column(String(32), default='DRAFT')
    data: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint('project_id', 'teacher_id', 'period_id'),)


class SocialAnnual(Entity, Base):
    __tablename__ = 'social_annuals'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey('periods.id'), index=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey('social_policies.id'))
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    state: Mapped[str] = mapped_column(String(32), default='DRAFT')
    data: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint('org_id', 'period_id'),)


class SocialResource(Entity, Base):
    __tablename__ = 'social_resources'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(32), default='DRAFT')
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
