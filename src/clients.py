from ossapi import OssapiAsync
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from src.config import (
    OSU_CLIENT_ID,
    OSU_CLIENT_SECRET,
    OSU_REDIRECT_URI,
    YOUTUBE_SCOPES,
    FORMS_SCOPES,
    DRIVE_SCOPES,
    TOKENS_DIR
)

osu = OssapiAsync(
    OSU_CLIENT_ID,
    OSU_CLIENT_SECRET,
    OSU_REDIRECT_URI,
    grant="authorization",
    token_key="osutoken",
    token_directory=str(TOKENS_DIR)
)


def get_youtube():
    creds = Credentials.from_authorized_user_file(TOKENS_DIR / "youtube_token.json", YOUTUBE_SCOPES)
    return build("youtube", "v3", credentials=creds)


def get_forms():
    creds = Credentials.from_authorized_user_file(TOKENS_DIR / "forms_token.json", FORMS_SCOPES)
    return build("forms", "v1", credentials=creds,
                 discoveryServiceUrl="https://forms.googleapis.com/$discovery/rest?version=v1",
                 static_discovery=False)


def get_drive():
    creds = creds = Credentials.from_authorized_user_file(TOKENS_DIR / "drive_token.json", DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds)
