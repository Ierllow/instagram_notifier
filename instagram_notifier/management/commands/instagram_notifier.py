from django.core.management.base import BaseCommand
from instagram_notifier.env_const import *
from instagram_notifier.models import *
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from typing import Optional
from itertools import takewhile, chain
from instagram_notifier.log_helper import log_error
from django.conf import settings
from django.core.signing import TimestampSigner
from pathlib import Path
import os, time, httpx, asyncio, instaloader, mimetypes, shutil

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class Command(BaseCommand):

    @log_error("instagram_notifier.handle")
    def handle(self, *args: tuple, **kwargs: dict) -> None:
        self._init()
        self._save_media()

    @log_error("instagram_notifier._init")
    def _init(self) -> None:
        self.loader = instaloader.Instaloader()
        session_path = Path.home() / f"instagram_notifier/session-{MY_INSTAGRAM_USERNAME}"
        self.loader.load_session_from_file(username=MY_INSTAGRAM_USERNAME, filename=str(session_path))

        options = Options()
        options.headless = True
        options.add_argument("--window-size=1080,1920")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(options=options)

    @log_error("instagram_notifier._save_post")
    def _save_post(self, post: instaloader.Post) -> None:
        shortcode = post.shortcode
        is_reel = self._is_reel_post(post)
        post_url = (f"https://www.instagram.com/reel/{shortcode}/" if is_reel else f"https://www.instagram.com/p/{shortcode}/")
        folder = f"downloads/{post.date_utc.strftime('%Y%m%d')}"
        os.makedirs(folder, exist_ok=True)
        screenshot_path = os.path.join(folder, f"{shortcode}.png")

        self.loader.download_post(post, target=folder)
        try:
            self.driver.get(post_url)
            time.sleep(3)
            self.driver.save_screenshot(screenshot_path)
        finally:
            self.driver.quit()

        msg = f"新しい投稿がありました！\n\n 投稿リンク:\n{post_url}"
        video_path = None
        for f in os.listdir(folder):
            if f.endswith(".mp4"):
                video_path = os.path.join(folder, f)
                media_target_folder = os.path.join(settings.MEDIA_ROOT, "instagram_media", post.date_utc.strftime('%Y%m%d'))
                os.makedirs(media_target_folder, exist_ok=True)
                new_path = os.path.join(media_target_folder, os.path.basename(video_path))
                shutil.move(video_path, new_path)

            if not is_reel:
                msg += f"\n\n 動画付き（長押しで保存できます）"
                msg += f"\n 動画のリンク（7日間有効）:\n{self._create_secure_media_url(post.shortcode)}"
            else:
                msg += f"\n\n リールのリンク（長押しで保存できます。7日間有効）:\n{self._create_secure_media_url(post.shortcode)}"

        asyncio.run(self._anotify_users(msg, screenshot_path, shortcode=shortcode))

        self._upload_drive(screenshot_path, folder_id=POST_DRIVE_FOLDER_ID)
        os.remove(screenshot_path)

        if video_path and self._upload_drive(video_path, folder_id=POST_DRIVE_FOLDER_ID):
            os.remove(video_path)

    @log_error("instagram_notifier._save_story")
    def _save_story(self, item: instaloader.StoryItem) -> None:
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

            msg += f"\n 動画のリンク（7日間有効）:\n{self._create_secure_media_url(item.mediaid)}"

            filepath = new_path
        else:
            msg += "\n\n 画像ストーリー（長押しで保存できます）"

        asyncio.run(self._anotify_users(msg, filepath, media_url=media_url))

        if self._upload_drive(filepath, folder_id=STORY_DRIVE_FOLDER_ID):
            os.remove(filepath)

    @log_error("instagram_notifier._upload_drive")
    def _upload_drive(self, filepath: str, folder_id: str = None) -> None:
        try:
            credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
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
    async def _anotify_users(self, msg: str, img_path: str, media_url: Optional[str] = None, shortcode: Optional[str] = None) -> None:
        is_notified = (media_url and NotificationLog.objects.filter(media_url=media_url).exists()) or (shortcode and NotificationLog.objects.filter(shortcode=shortcode).exists())
        if is_notified:
            return
        new_notification_log_list = []
        for user in LineUser.objects.iterator():
            headers = {"Authorization": f'Bearer {LINE_NOTIFY_TOKEN}'}
            files = {"imageFile": open(img_path, "rb")}
            data = {"message": msg}
            mine_type, _ = mimetypes.guess_type(img_path)
            mine_type = mine_type or "application/octet-stream"
            with open(img_path, "rb") as f:
                files = {"imageFile": (os.path.basename(img_path), f.read(), mine_type)}
                async with httpx.AsyncClient() as client:
                    response = await client.post("https://notify-api.line.me/api/notify", headers=headers, data=data, files=files)
                response.raise_for_status()

            new_notification_log_list.append(NotificationLog.create_for_post(user, shortcode) if shortcode else NotificationLog.create_for_story(user, media_url))

        if new_notification_log_list:
            NotificationLog.objects.bulk_create(new_notification_log_list)

    @log_error("instagram_notifier._create_secure_media_url")
    def _create_secure_media_url(self, shortcode: str) -> str:
        token = TimestampSigner().sign(shortcode)
        return f"{SITE_URL}/secure-media/{token}/"

    @log_error("instagram_notifier._save_media")
    def _save_media(self) -> None:
        profile = instaloader.Profile.from_username(self.loader.context, TARGET_INSTAGRAM_USERNAME)

        default_last_time = datetime.min.replace(tzinfo=None)

        post_log = FetchLog.objects.filter(kind=FetchKind.POST).first()
        last_post_time = post_log.last_checked_at if post_log else default_last_time
        new_posts = takewhile(lambda p: p.date_utc > last_post_time, profile.get_posts())
        for post in new_posts:
            self._save_post(post)

        story_log = FetchLog.objects.filter(kind=FetchKind.STORY).first()
        last_story_time = story_log.last_checked_at if story_log else default_last_time
        new_stories = filter(lambda item: item.date_utc > last_story_time, chain.from_iterable(story.get_items() for story in self.loader.get_stories(userids=[profile.userid])))
        for item in new_stories:
            self._save_story(item)

        FetchLog.objects.bulk_create([
            FetchLog(kind=FetchKind.POST, last_checked_at=max(post.date_utc for post in new_posts)),
            FetchLog(kind=FetchKind.STORY, last_checked_at=max(item.date_utc for item in new_stories)),
            ])

    def _is_reel_post(self, post: instaloader.Post) -> bool:
        try:
            # reel動画かの判別するために_full_metadataを使用
            # プライベートのため非推奨の書き方 使い方には注意
            return post._full_metadata.get("product_type") == "reels"
        except Exception:
            return False