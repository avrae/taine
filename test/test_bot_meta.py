from bot import GITHUB_REPO, OWNER_ID, BUG_CHAN, DDB_CHAN, FEATURE_CHAN, TRACKER_CHAN, bot
from cogs.aliases import ALIAS_REPO


def test_constants():
    assert GITHUB_REPO == 'avrae/avrae'
    assert OWNER_ID == "187421759484592128"
    assert BUG_CHAN == "336792750773239809"
    assert DDB_CHAN == "463580965810208768"
    assert FEATURE_CHAN == "297190603819843586"
    assert TRACKER_CHAN == "360855116057673729"
    assert bot.command_prefix == '~'
    assert ALIAS_REPO == "avrae/avrae-docs"
