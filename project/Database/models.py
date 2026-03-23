from typing import List

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    projects: Mapped[List['Project']] = relationship(back_populates='owner')
    project_participants: Mapped[List['ProjectParticipant']] = relationship(back_populates='user')


class Project(Base):
    __tablename__ = 'projects'

    project_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), nullable=False)

    # Relationships
    owner: Mapped[User] = relationship(back_populates='projects')
    projects_in_dev: Mapped[List['ProjectParticipant']] = relationship(
        back_populates='project', cascade='all, delete-orphan')
    documents: Mapped[List['Documents']] = relationship(back_populates='project', cascade='all, delete-orphan')


class ProjectParticipant(Base):
    __tablename__ = 'project_participants'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.project_id'), primary_key=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates='project_participants')
    project: Mapped[Project] = relationship(back_populates='projects_in_dev')


class Documents(Base):
    __tablename__ = 'documents'

    document_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.project_id'), nullable=False)

    # Relationships
    project: Mapped[Project] = relationship(back_populates='documents')
