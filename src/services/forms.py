from dateutil import parser
from datetime import datetime
from src.clients import get_forms, osu
from src.db.scores import get_score
from src.db.status import get_status
from src.db.mongo import db
from src.config import FORM_ID, COUNTRY_CODE


async def get_form_resp():
    update_status = get_status(db, COUNTRY_CODE)
    service = get_forms()
    result = await service.forms().responses().list(formId=FORM_ID).execute()
    score_ids = []
    if 'responses' not in result:
        return score_ids
    for resp in result['responses']:
        resp_time_obj = parser.isoparse(resp['lastSubmittedTime'])
        resp_timestamp = resp_time_obj.timestamp()
        if resp_timestamp - update_status['form_updated'] >= 0:
            score_id = resp['answers']['7f0c0670']['textAnswers']['answers'][0]['value']
            score_obj = await osu.score(score_id=score_id)
            if not score_obj:
                continue
            score = get_score(db, {'score_id': score_obj.id})
            if score or not score_obj.replay:
                continue
            score_ids.append(score_obj.id)

    now = datetime.now()
    timestamp_now = datetime.timestamp(now)
    await update_status(COUNTRY_CODE, {'form_updated': timestamp_now})

    return score_ids
