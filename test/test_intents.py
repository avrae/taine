from bot import bot


def test_intents_match_developer_portal():
    assert bot.intents.message_content
    assert not bot.intents.members
    assert not bot.intents.presences
