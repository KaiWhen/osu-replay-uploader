from datetime import datetime
import os
from src.clients import get_forms, osu
from src.db.scores import get_score
from src.db.status import get_status, update_status
from src.db.mongo import db
from src.services.drive import delete_file, download_file
from src.utils import to_rfc3339, verify_replay_file
from src.config import FORM_ID, FORM_SCORE_ANSWER_ID, FORM_FILE_ANSWER_ID, COUNTRY_CODE, REPLAYS_DIR


async def get_form_resp():
    status = await get_status(db, COUNTRY_CODE)
    last_updated_timestamp = status['form_updated']
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
        if FORM_FILE_ANSWER_ID in resp['answers']:
            file_answer = resp['answers'][FORM_FILE_ANSWER_ID]['fileUploadAnswers']['answers'][0]
            file_id = file_answer['fileId']

        score = {
            'score_id': score_id,
            'file_id': file_id,
            'valid': False,
            'err': None
        }
        try:
            score_obj = await osu.score(score_id=score_id)
        except:
            score['err'] = "Invalid score ID."
            scores.append(score)
            continue
        if score._user.country_code != "IE":
            score['err'] = "This player is not from Ireland bruh"
            scores.append(score)
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
                await delete_file(file_id)
                score['file_id'] = "DELETED"
                continue
            replay_path = REPLAYS_DIR / f"{score_id}.osr"
            try:
                await download_file(file_id, replay_path)
            except Exception as e:
                score['err'] = f"Failed to download replay from Drive: {e}"
                scores.append(score)
                continue
            if not verify_replay_file(str(replay_path)):
                score['err'] = f"Either a corrupt replay file or this mf tried to submit a different file type"
                scores.append(score)
                os.remove(replay_path)
                await delete_file(file_id)
                score['file_id'] = "DELETED"
                continue
        score['valid'] = True
        scores.append(score)

    now = datetime.now()
    timestamp_now = datetime.timestamp(now)
    await update_status(db, COUNTRY_CODE, {'form_updated': timestamp_now})

    return scores
