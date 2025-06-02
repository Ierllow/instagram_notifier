from django.core.management.base import BaseCommand
from django.db import transaction
from instagram_notifier.models import *
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from typing import Optional
from itertools import takewhile
from instagram_notifier.log_helper import log_error
from django.conf import settings
from django.core.signing import TimestampSigner
import os, time, httpx, asyncio, instaloader, mimetypes, shutil
from itertools import chain

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class Command(BaseCommand):

    @log_error("instagram_notifier.handle")
    def handle(self, *args: tuple, **kwargs: dict) -> None:
        self.loader = instaloader.Instaloader()

        profile = instaloader.Profile.from_username(self.loader.context, os.getenv("INSTAGRAM_USERNAME"))

        default_last_time = datetime.min.replace(tzinfo=None)
        last_post_time = (log := FetchLog.objects.filter(kind=FetchKind.POST).first().last_checked_at if log else default_last_time)
        last_story_time = (log := FetchLog.objects.filter(kind=FetchKind.STORY).first().last_checked_at if log else default_last_time)

        new_posts = takewhile(lambda p: p.date_utc <= last_post_time, profile.get_posts())
        for post in new_posts:
            self.__save_post(post)

        new_stories = chain.from_iterable(story.get_items() for story in self.loader.get_stories(userids=[profile.userid]))
        for item in new_stories:
            self.__save_story(item, last_story_time)

    @log_error("instagram_notifier.__save_post")
    def __save_post(self, post: instaloader.Post) -> None:
        shortcode = post.shortcode
        post_url = f"https://www.instagram.com/p/{shortcode}/"
        folder = f"downloads/{post.date_utc.strftime('%Y%m%d')}"
        os.makedirs(folder, exist_ok=True)
        screenshot_path = os.path.join(folder, f"{shortcode}.png")

        self.loader.download_post(post, target=folder)
        url = f"https://www.instagram.com/p/{shortcode}/"
        options = Options()
        options.headless = True
        options.add_argument("--window-size=1080,1920")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            time.sleep(3)
            driver.save_screenshot(screenshot_path)
        finally:
            driver.quit()

        msg = f"新しい投稿がありました！\n\n 投稿リンク:\n{post_url}"
        video_path = None
        for f in os.listdir(folder):
            if f.endswith(".mp4"):
                video_path = os.path.join(folder, f)
                media_target_folder = os.path.join(settings.MEDIA_ROOT, "instagram_media", post.date_utc.strftime('%Y%m%d'))
                os.makedirs(media_target_folder, exist_ok=True)
                new_path = os.path.join(media_target_folder, os.path.basename(video_path))
                shutil.move(video_path, new_path)

                msg += (
                    f"\n\n 動画付き（長押しで保存できます）"
                    f"\n 動画のリンク（7日間有効）:\n{self._create_secure_media_url(post.shortcode)}"
                )

        asyncio.run(self._notify_users_async(msg, screenshot_path, shortcode=shortcode))

        post_folder_id = os.getenv("DRIVE_POST_FOLDER_ID")
        self._upload_drive(screenshot_path, folder_id=post_folder_id)
        os.remove(screenshot_path)

        if video_path and self._upload_drive(video_path, folder_id=post_folder_id):
            os.remove(video_path)

        with transaction.atomic():
            FetchLog.objects.update_or_create(kind=FetchKind.POST, defaults={"last_checked_at": post.date_utc})

    @log_error("instagram_notifier.__save_story")
    def __save_story(self, item: instaloader.StoryItem, last_time: datetime) -> None:
        if item.date_utc <= last_time:
            return

        media_url = item.video_url if item.is_video else item.url
        if NotificationLog.objects.filter(media_url=media_url).exists():
            return

        folder = f"downloads/{item.date_utc.strftime('%Y%m%d')}"
        os.makedirs(folder, exist_ok=True)
        self.loader.download_storyitem(item, target=folder)

        filename = media_url.split("/")[-1].split("?")[0]
        filepath = os.path.join(folder, filename)
        msg = "新しいストーリーが追加されました！"

        if item.is_video:
            date_folder = item.date_utc.strftime('%Y%m%d')
            media_target_folder = os.path.join(settings.MEDIA_ROOT, "instagram_media", date_folder)
            os.makedirs(media_target_folder, exist_ok=True)

            new_path = os.path.join(media_target_folder, filename)
            shutil.move(filepath, new_path)

            msg += (
                f"\n\n 動画付き（長押しで保存できます）"
                f"\n 動画のリンク（7日間有効）:\n{self._create_secure_media_url(item.mediaid)}"
            )

            filepath = new_path
        else:
            msg += "\n\n 画像ストーリー（長押しで保存できます）"

        asyncio.run(self._notify_users_async(msg, filepath, media_url=media_url))

        if self._upload_drive(filepath, folder_id=os.getenv("DRIVE_STORY_FOLDER_ID")):
            os.remove(filepath)

        with transaction.atomic():
            FetchLog.objects.update_or_create(kind=FetchKind.STORY, defaults={"last_checked_at": item.date_utc})

    @log_error("instagram_notifier._upload_drive")
    def _upload_drive(self, filepath: str, folder_id: str = None) -> None:
        try:
            credentials = service_account.Credentials.from_service_account_file(os.getenv("SERVICE_ACCOUNT_FILE"), scopes=SCOPES)
            service = build('drive', 'v3', credentials=credentials)

            file_metadata = {'name': os.path.basename(filepath),}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(filepath, resumable=True)
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            return True
        except Exception:
            return False

    @log_error("instagram_notifier._notify_users_async")
    async def _notify_users_async(self, msg: str, img_path: str, media_url: Optional[str] = None, shortcode: Optional[str] = None) -> None:
        objects = NotificationLog.objects
        is_notified = (media_url and objects.filter(media_url=media_url).exists()) or (shortcode and objects.filter(shortcode=shortcode).exists())
        if is_notified:
            return
        users = LineUser.objects.all()
        for user in users:
            headers = {"Authorization": f'Bearer {os.getenv("LINE_NOTIFY_TOKEN")}'}
            files = {"imageFile": open(img_path, "rb")}
            data = {"message": msg}
            mine_type, _ = mimetypes.guess_type(img_path)
            mine_type = mine_type or "application/octet-stream"
            with open(img_path, "rb") as f:
                files = {"imageFile": (os.path.basename(img_path), f.read(), mine_type)}
                async with httpx.AsyncClient() as client:
                    response = await client.post("https://notify-api.line.me/api/notify", headers=headers, data=data, files=files)
                response.raise_for_status()
        with transaction.atomic():
            if shortcode:
                objects.create(user=None, media_type=MediaType.POST, shortcode=shortcode)
            elif media_url:
                objects.create(user=None, media_type=MediaType.STORY, media_url=media_url)

    @log_error("instagram_notifier._create_secure_media_url")
    def _create_secure_media_url(self, shortcode: str) -> str:
        token = TimestampSigner().sign(shortcode)
        return f"{os.getenv('SITE_URL')}/secure-media/{token}/"
