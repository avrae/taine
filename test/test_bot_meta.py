from bot import bot
from constants import BUG_LISTEN_CHANS, REPO_ID_MAP, TRACKER_CHAN


def test_constants():
    """This test makes sure we don't push testing constants to production"""
    assert BUG_LISTEN_CHANS == [
        {
            "id": 336792750773239809,  # bug-reports
            "identifier": "AVR",
            "repo": "avrae/avrae"
        },
        {
            "id": 297190603819843586,  # feature-request
            "identifier": "AFR",
            "repo": "avrae/avrae"
        },
        {
            "id": 487486995527106580,  # web-reports
            "identifier": "WEB",
            "repo": "avrae/avrae.io"
        },
        {
            "id": 590611030611197962,  # api-reports
            "identifier": "API",
            "repo": "avrae/avrae-service"
        },
        {
            "id": 590611115734728704,  # taine-reports
            "identifier": "TNE",
            "repo": "avrae/taine"
        }
    ]

    assert REPO_ID_MAP == {
        "avrae/avrae": "AVR",
        "avrae/avrae.io": "WEB",
        "avrae/avrae-service": "API",
        "avrae/taine": "TNE"
    }

    assert TRACKER_CHAN == 360855116057673729
    assert bot.command_prefix == '~'
