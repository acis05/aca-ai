from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dateutil.relativedelta import relativedelta
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import hashlib
import hmac
import secrets

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'storage' / 'mapping.db'
DATABASE_URL = os.getenv('DATABASE_URL') or f"sqlite:///{DB_PATH}"
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif DATABASE_URL.startswith('postgresql://') and '+psycopg' not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()
    return f'pbkdf2_sha256${iterations}${salt}${digest}'


def verify_password(encoded: str, password: str) -> bool:
    try:
        algo, iterations, salt, expected = encoded.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(190), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='user')
    is_enabled = Column(Boolean, nullable=False, default=True)
    active_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    mappings = relationship('MappingProfile', back_populates='user', cascade='all, delete-orphan')

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def subscription_active(self):
        if self.is_admin:
            return True
        if not self.is_enabled or not self.active_until:
            return False
        dt = self.active_until
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= utcnow()


class MappingProfile(Base):
    __tablename__ = 'mapping_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    name = Column(String(160), nullable=False)
    platform = Column(String(100), nullable=False)
    module = Column(String(120), nullable=False)
    source_signature = Column(String(100), nullable=True)
    mapping_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    user = relationship('User', back_populates='mappings')


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    admin_email = os.getenv('ADMIN_EMAIL', 'admin@aca-ai.local').strip().lower()
    admin_password = os.getenv('ADMIN_PASSWORD', 'ChangeMe123!')
    admin_name = os.getenv('ADMIN_NAME', 'ACA Admin')
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == admin_email))
        if not admin:
            db.add(User(name=admin_name, email=admin_email, password_hash=hash_password(admin_password), role='admin', is_enabled=True))
            db.commit()


def authenticate(email, password):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == (email or '').strip().lower()))
        if not user or not verify_password(user.password_hash, password or ''):
            return None
        return user_to_dict(user)


def user_to_dict(user):
    return {
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'role': user.role,
        'is_enabled': bool(user.is_enabled),
        'active_until': user.active_until,
        'created_at': user.created_at,
        'subscription_active': user.subscription_active,
        'is_admin': user.is_admin,
    }


def get_user(user_id):
    with SessionLocal() as db:
        user = db.get(User, int(user_id)) if user_id else None
        return user_to_dict(user) if user else None


def list_users():
    with SessionLocal() as db:
        users = db.scalars(select(User).order_by(User.role.asc(), User.created_at.desc())).all()
        return [user_to_dict(u) for u in users]


def create_user(name, email, password, months):
    email = (email or '').strip().lower()
    if not email or not password:
        raise ValueError('Email dan password wajib diisi')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise ValueError('Email sudah terdaftar')
        active_until = utcnow() + relativedelta(months=int(months))
        user = User(name=(name or email).strip(), email=email, password_hash=hash_password(password), role='user', is_enabled=True, active_until=active_until)
        db.add(user)
        db.commit(); db.refresh(user)
        return user_to_dict(user)


def extend_user(user_id, months):
    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if not user or user.role == 'admin':
            raise ValueError('User tidak ditemukan')
        base = user.active_until
        if not base or (base.replace(tzinfo=timezone.utc) if base.tzinfo is None else base) < utcnow():
            base = utcnow()
        user.active_until = base + relativedelta(months=int(months))
        user.is_enabled = True
        db.commit(); db.refresh(user)
        return user_to_dict(user)


def set_user_enabled(user_id, enabled):
    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if not user or user.role == 'admin':
            raise ValueError('User tidak ditemukan')
        user.is_enabled = bool(enabled)
        db.commit(); db.refresh(user)
        return user_to_dict(user)


def reset_user_password(user_id, new_password):
    if not new_password:
        raise ValueError('Password baru wajib diisi')
    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if not user or user.role == 'admin':
            raise ValueError('User tidak ditemukan')
        user.password_hash = hash_password(new_password)
        db.commit()


def save_profile(name, source_signature, mapping, schema, user_id=None):
    with SessionLocal() as db:
        p = MappingProfile(user_id=user_id, name=name, platform=schema['platform'], module=schema['module'], source_signature=source_signature, mapping_json=json.dumps(mapping, ensure_ascii=False))
        db.add(p); db.commit(); db.refresh(p)
        return p.id


def list_profiles(user_id=None, is_admin=False):
    with SessionLocal() as db:
        stmt = select(MappingProfile).order_by(MappingProfile.id.desc()).limit(50)
        if not is_admin:
            stmt = stmt.where(MappingProfile.user_id == user_id)
        rows = db.scalars(stmt).all()
        return [{'id': r.id, 'name': r.name, 'platform': r.platform, 'module': r.module, 'source_signature': r.source_signature, 'created_at': r.created_at} for r in rows]


def get_profile(profile_id, user_id=None, is_admin=False):
    with SessionLocal() as db:
        p = db.get(MappingProfile, int(profile_id))
        if not p or (not is_admin and p.user_id != user_id):
            return None
        return {'id': p.id, 'name': p.name, 'platform': p.platform, 'module': p.module, 'source_signature': p.source_signature, 'created_at': p.created_at, 'mapping': json.loads(p.mapping_json)}
