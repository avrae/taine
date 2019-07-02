import json

from lib import db


async def run():
    with open("../data/reports.json") as f:
        old_reports = json.load(f)
    with open("../data/reportnums.json") as f:
        old_reportnums = json.load(f)

    for identifier, num in old_reportnums.items():
        db.reportnums.put_item(Item={
            "identifier": identifier,
            "num": num
        })

    for old_report in old_reports.values():
        print(old_report['report_id'])

        # sentinel values in case of null secondary index value
        if old_report['message'] is None:
            old_report['message'] = 0
        if old_report['github_issue'] is None:
            old_report['github_issue'] = 0

        # no empty strings
        if old_report['title'] == '':
            old_report['title'] = "NO TITLE"
        for attachment in old_report['attachments']:
            if attachment['message'] == '':
                attachment['message'] = None

        db.reports.put_item(Item=old_report)


if __name__ == '__main__':
    import asyncio

    asyncio.get_event_loop().run_until_complete(run())
