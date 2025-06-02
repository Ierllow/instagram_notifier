from django.views import View
from django.http import FileResponse, HttpRequest, HttpResponse, Http404
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.conf import settings
import os, glob

class SecureMediaView(View):
    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        signer = TimestampSigner()
        try:
            shortcode = signer.unsign(token, max_age=604800)
        except (SignatureExpired, BadSignature):
            raise Http404("無効または期限切れのトークンです。")

        base_dir = os.path.join(settings.MEDIA_ROOT, "instagram_media")
        pattern = os.path.join(base_dir, "*", f"{shortcode}.mp4")
        matches = glob.glob(pattern)
        file_path =  matches[0] if matches else None
        if not file_path or not os.path.exists(file_path):
            raise Http404("動画ファイルが見つかりません。")

        return FileResponse(open(file_path, "rb"), content_type="video/mp4")
