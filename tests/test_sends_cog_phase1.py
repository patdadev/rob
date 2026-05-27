from rob.discord.cogs import sends as sends_cog


def test_legacy_manual_send_methods_are_supported():
    assert sends_cog._MANUAL_METHODS == ["cashapp", "venmo", "paypal", "onlyfans", "loyalfans", "youpay", "other"]
