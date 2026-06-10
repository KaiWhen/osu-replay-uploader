from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# paths
BASE_DIR = Path(__file__).parent.parent
TOKENS_DIR = BASE_DIR / "tokens/"
REPLAYS_DIR = BASE_DIR / "replays/"
THUMBNAILS_DIR = BASE_DIR / "thumbnails/"
VIDEOS_DIR = BASE_DIR / "videos/"
MAPS_DIR = BASE_DIR / "maps/"

# mongo
MONGO_URI = os.environ["MONGO_URI"]

# osu
OSU_CLIENT_ID = os.environ["OSU_CLIENT_ID"]
OSU_CLIENT_SECRET = os.environ["OSU_CLIENT_SECRET"]
OSU_REDIRECT_URI = "http://localhost:3000"

# google
GOOGLE_REDIRECT_URI = "http://localhost:8080/oauth/callback"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl", "https://www.googleapis.com/auth/youtube.upload"]
FORMS_SCOPES = ["https://www.googleapis.com/auth/forms.responses.readonly"]
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.metadata', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/drive.file']
FORM_ID = "1quic99kn_XTBrMaZA8un_j3Xr5Xk98wY2-bYwteQx5s"
FORM_SCORE_ANSWER_ID = "7f0c0670"
FORM_FILE_ANSWER_ID = "168ed010"

# discord
DISCORD_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_USER_ID = 282617728320405514
DISCORD_NOTIFICATION_CHANNEL_ID = 257559748075847680
DISCORD_APPROVAL_CHANNEL_ID = 1110508875238604871
# DISCORD_JOBS_FEED_CHANNEL_ID = 0

# o!rdr
ORDR_API_URL = "https://apis.issou.best/ordr/renders"
# ORDR_KEY = os.environ["ORDR_KEY"]
DEFAULT_SKIN_ID = "7496"
SKIN_URL = "https://apis.issou.best/ordr/skins/custom"

# worker
WORKER_POLL_INTERVAL = 30
JOB_MAX_ATTEMPTS = 6
JOB_RETRY_DELAY = 60
STALE_JOB_THRESHOLD = 30*60

# other
COUNTRY_CODE = 'IE'
