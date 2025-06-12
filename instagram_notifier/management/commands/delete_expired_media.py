from django.core.management.base import BaseCommand
from django.conf import settings
from instagram_notifier.models import *
from itertools import takewhile
from instagram_notifier.log_helper import log_error
import os, datetime, glob

class Command(BaseCommand):

    @log_error("delete_expired_media.handle")
    def handle(self, *args: tuple, **kwargs: dict) -> None:
        folder = os.path.join(settings.MEDIA_ROOT, "instagram_media")
        expire_seconds = 7 * 24 * 60 * 60
        now = datetime.datetime.now()
        mp4_files = glob.glob(os.path.join(folder, "**", "*.mp4"), recursive=True)
        deletable_files = takewhile(lambda p: os.path.getmtime(p) < now - datetime.timedelta(seconds=expire_seconds), mp4_files)
        new_media_deletion_log_list = []
        for path in deletable_files:
            new_media_deletion_log_list.append(MediaDeletionLog.create(os.path.basename(path), os.path.splitext(os.path.basename(path))[0]))
            os.remove(path)

        if new_media_deletion_log_list:
            MediaDeletionLog.objects.bulk_create(new_media_deletion_log_list)

        folder_path = os.path.dirname(path)
        if os.path.exists(folder_path) and not os.listdir(folder_path):
            os.rmdir(folder_path)
