from lib.reports import Report


def test_create():
    report = Report(1, "AVR-001", "test", 6, 0, [], None)
    assert report.reporter == 1
    assert report.report_id == "AVR-001"
    assert report.title == "test"
    assert report.severity == 6
    assert report.verification == 0
    assert report.attachments == []
    assert report.message is None

    report_dict = report.to_dict()
    new_report = Report.from_dict(report_dict)
    assert report.__dict__ == new_report.__dict__
