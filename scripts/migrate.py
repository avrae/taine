import json

from lib.reports import Report


def run():
    with open("reports.json") as f:
        reports = json.load(f)

    for report_id, report in reports.items():
        print(report_id)
        for attachment in report['attachments']:
            try:
                attachment['author'] = int(attachment['author'])
            except ValueError:
                pass
            attachment['message'] = attachment.pop('msg')

        new_report = Report.from_dict(report)

        try:
            new_report.reporter = int(new_report.reporter)
        except ValueError:
            pass

        if new_report.message:
            new_report.message = int(new_report.message)

        new_report.is_bug = new_report.report_id.startswith("AFR")
        new_report.subscribers = list(map(int, new_report.subscribers))

        reports[report_id] = new_report.to_dict()

    with open("new-reports.json", 'w') as f:
        json.dump(reports, f)


if __name__ == '__main__':
    run()
