import asyncio
from aiohttp import web
from google_auth_oauthlib.flow import Flow
from src.config import GOOGLE_REDIRECT_URI, YOUTUBE_SCOPES, FORMS_SCOPES, TOKENS_DIR, DRIVE_SCOPES


CODE_RESULT = None


async def handle_callback(request):
    global CODE_RESULT
    CODE_RESULT = request.query.get("code")
    return web.Response(text="✅ Authorized! You can close this tab.")


async def authorize(scopes: list[str], token_filename: str):
    global CODE_RESULT
    CODE_RESULT = None

    flow = Flow.from_client_secrets_file(
        "tokens/client_secrets.json",
        scopes=scopes,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print(f"\nAuthorizing {token_filename}...\nOpen this URL:\n{url}\n")

    while CODE_RESULT is None:
        await asyncio.sleep(1)

    flow.fetch_token(code=CODE_RESULT)
    TOKENS_DIR.mkdir(exist_ok=True)
    (TOKENS_DIR / token_filename).write_text(flow.credentials.to_json())
    print(f"Saved {token_filename}\n")


async def main():
    # start callback server
    app = web.Application()
    app.router.add_get("/oauth/callback", handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

    #await authorize(YOUTUBE_SCOPES, "youtube_token.json")
    #await authorize(FORMS_SCOPES, "forms_token.json")
    await authorize(DRIVE_SCOPES, "drive_token.json")
    print("All tokens saved!")


asyncio.run(main())
