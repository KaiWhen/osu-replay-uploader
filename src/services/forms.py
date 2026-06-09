from datetime import datetime
from src.clients import get_forms, osu
from src.db.scores import get_score
from src.db.status import get_status
from src.db.mongo import db
from src.services.drive import download_file
from src.utils import to_rfc3339
from src.config import FORM_ID, FORM_SCORE_ANSWER_ID, FORM_FILE_ANSWER_ID, COUNTRY_CODE, REPLAYS_DIR


async def get_form_resp():
    update_status = await get_status(db, COUNTRY_CODE)
    last_updated_timestamp = update_status['form_updated']
    last_updated_rfc3339 = to_rfc3339(last_updated_timestamp)
    forms_service = get_forms()
    result = forms_service.forms().responses().list(
        formId=FORM_ID,
        filter=f"timestamp >= {last_updated_rfc3339}"
    ).execute()
    scores = []
    if 'responses' not in result:
        return scores

    for resp in result['responses']:
        score_id = resp['answers'][FORM_SCORE_ANSWER_ID]['textAnswers']['answers'][0]['value']
        file_answer = None
        file_id = None
        if resp['answers'][FORM_FILE_ANSWER_ID]:
            file_answer = resp['answers'][FORM_FILE_ANSWER_ID]['fileUploadAnswers']['answers'][0]
            file_id = file_answer['fileId']

        score = {
            'score_id': score_id,
            'file_id': file_id,
            'valid': False,
            'err': None
        }
        score_obj = await osu.score(score_id=score_id)
        if not score_obj:
            score['err'] = "Invalid score ID."
            scores.add(score)
            continue
        score_exists = await get_score(db, {'score_id': score_obj.id})
        if score_exists:
            score['err'] = "Score has already been submitted."
            scores.append(score)
            continue

        if not score_obj.replay:
            if not file_answer:
                score['err'] = "No downloadable/submitted replay data."
                scores.append(score)
                continue
            if file_answer['mimeType'] != "application/x-osu-replay":
                score['err'] = "Invalid file type."
                scores.append(score)
                continue
            try:
                await download_file(file_id, REPLAYS_DIR / f"{score_id}.osr")
            except Exception as e:
                score['err'] = f"Failed to download replay from Drive: {e}"
                scores.append(score)
                continue
        score['valid'] = True
        scores.append(score)

    now = datetime.now()
    timestamp_now = datetime.timestamp(now)
    # await update_status(COUNTRY_CODE, {'form_updated': timestamp_now})

    return scores
