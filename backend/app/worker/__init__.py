"""
Celery app entry point for the worker command.
Imports the celery_app instance from worker/tasks.py.
"""

from app.worker.tasks import celery_app

__all__ = ["celery_app"]
