
from django.db import models

class LineUser(models.Model):
    uid = models.BigIntegerField(primary_key=True, db_index=True)
    followed_at = models.DateTimeField()

class MediaType(models.TextChoices):
    POST = 'post', 'Post'
    STORY = 'story', 'Story'

class NotificationLog(models.Model):
    user = models.ForeignKey(LineUser, on_delete=models.CASCADE, null=True)
    media_type = models.CharField(max_length=10, choices=MediaType.choices, db_index=True)
    shortcode = models.CharField(max_length=100, null=True, blank=True)
    media_url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class FetchKind(models.TextChoices):
    POST = 'post', 'Post'
    STORY = 'story', 'Story'

class FetchLog(models.Model):
    kind = models.CharField(max_length=10, choices=FetchKind.choices, db_index=True)
    last_checked_at = models.DateTimeField()

class ErrorLog(models.Model):
    location = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class MediaDeletionLog(models.Model):
    file_path = models.CharField(max_length=255)
    shortcode = models.CharField(max_length=64)
    deleted_at = models.DateTimeField(auto_now_add=True)
