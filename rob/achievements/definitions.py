from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AchievementRarity = Literal["common", "uncommon", "rare", "epic", "legendary", "secret"]
AchievementCategory = Literal[
    "count",
    "sends_domme",
    "sends_sub",
    "leaderboard",
    "throne_tracking",
    "inactivity",
    "maintenance",
    "misc",
    "secret",
]

RARITY_ORDER: dict[AchievementRarity, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "secret": 5,
}

RARITY_LABEL: dict[AchievementRarity, str] = {
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "epic": "Epic",
    "legendary": "Legendary",
    "secret": "Secret",
}

CATEGORY_LABEL: dict[AchievementCategory, str] = {
    "count": "Counting",
    "sends_domme": "Sends (Domme)",
    "sends_sub": "Sends (Sub)",
    "leaderboard": "Leaderboard",
    "throne_tracking": "Throne Tracking",
    "inactivity": "Inactivity",
    "maintenance": "Maintenance",
    "misc": "Misc",
    "secret": "Secret",
}


@dataclass(frozen=True)
class AchievementDefinition:
    key: str
    title: str
    description: str
    category: AchievementCategory
    rarity: AchievementRarity
    hidden: bool = False
    repeatable: bool = False
    enabled: bool = True
    trigger_type: str | None = None
    trigger_value: str | int | None = None

    @property
    def rarity_rank(self) -> int:
        return RARITY_ORDER.get(self.rarity, 0)

    @property
    def rarity_label(self) -> str:
        return RARITY_LABEL.get(self.rarity, self.rarity.title())

    @property
    def category_label(self) -> str:
        return CATEGORY_LABEL.get(self.category, self.category.replace("_", " ").title())


def _a(
    key: str,
    title: str,
    description: str,
    *,
    category: AchievementCategory,
    rarity: AchievementRarity,
    hidden: bool = False,
    enabled: bool = True,
    trigger_type: str | None = None,
    trigger_value: str | int | None = None,
) -> AchievementDefinition:
    return AchievementDefinition(
        key=key,
        title=title,
        description=description,
        category=category,
        rarity=rarity,
        hidden=hidden,
        enabled=enabled,
        trigger_type=trigger_type,
        trigger_value=trigger_value,
    )


ACHIEVEMENTS: tuple[AchievementDefinition, ...] = (
    _a(
        "count_start",
        "In the Beninging…",
        "You started the count. This is either brave or deeply foolish.",
        category="count",
        rarity="common",
        trigger_type="count_number",
        trigger_value=1,
    ),
    _a(
        "count_10",
        "Double Digits",
        "You counted to 10. Humanity may yet survive.",
        category="count",
        rarity="common",
        trigger_type="count_number",
        trigger_value=10,
    ),
    _a(
        "count_67",
        "The 67 Incident",
        "You said 67. Rob doesn’t know why this matters, but apparently it does.",
        category="count",
        rarity="uncommon",
        trigger_type="count_number",
        trigger_value=67,
    ),
    _a(
        "count_69",
        "Nice",
        "Hehe, that's a funny number.",
        category="count",
        rarity="uncommon",
        trigger_type="count_number",
        trigger_value=69,
    ),
    _a(
        "count_100",
        "Hundredth Counter",
        "You were the one to say 100.",
        category="count",
        rarity="uncommon",
        trigger_type="count_number",
        trigger_value=100,
    ),
    _a(
        "count_420",
        "Suspiciously Herbal",
        "You said 420. Rob is pretending not to notice.",
        category="count",
        rarity="rare",
        trigger_type="count_number",
        trigger_value=420,
    ),
    _a(
        "count_666",
        "Slightly Cursed",
        "You said 666. The count feels haunted now.",
        category="count",
        rarity="rare",
        trigger_type="count_number",
        trigger_value=666,
    ),
    _a(
        "count_1000",
        "Thousandth Counter",
        "You were the one to say 1000. That deserves a tiny parade.",
        category="count",
        rarity="rare",
        trigger_type="count_number",
        trigger_value=1000,
    ),
    _a(
        "count_1234",
        "Numerically Suspicious",
        "You said 1234. Did the count restart?",
        category="count",
        rarity="rare",
        trigger_type="count_number",
        trigger_value=1234,
    ),
    _a(
        "count_4321",
        "Suspiciously Numerical",
        "You said 4321. That’s not a number, that’s a countdown in disguise.",
        category="count",
        rarity="epic",
        trigger_type="count_number",
        trigger_value=4321,
    ),
    _a(
        "count_5000",
        "Five Thousand?!",
        "You helped drag the count all the way to 5000. Rob is impressed and mildly concerned.",
        category="count",
        rarity="epic",
        trigger_type="count_number",
        trigger_value=5000,
    ),
    _a(
        "count_10000",
        "Count Goblin Supreme",
        "You reached 10000. At this point, it’s not a count. It’s a lifestyle.",
        category="count",
        rarity="legendary",
        trigger_type="count_number",
        trigger_value=10000,
    ),
    _a(
        "count_first_mistake",
        "Numbers Are Hard",
        "You made your first counting mistake. Honestly? Relatable.",
        category="count",
        rarity="common",
        trigger_type="count_failure",
        trigger_value="first",
    ),
    _a(
        "count_sub_recovered_own_mistake",
        "That Was Close…",
        "You recovered the count after your own mistake. Redemption arc complete.",
        category="count",
        rarity="uncommon",
        trigger_type="count_recovery",
        trigger_value="sub_own",
    ),
    _a(
        "count_sub_recovered_domme_mistake",
        "Here’s Your Gold Star",
        "You fixed a dom/me’s count mistake. Tiny hero behaviour.",
        category="count",
        rarity="uncommon",
        trigger_type="count_recovery",
        trigger_value="sub_saved_domme",
    ),
    _a(
        "count_domme_saved_by_sub",
        "What Mistake? I Don’t See One",
        "A sub recovered your happy little accident..",
        category="count",
        rarity="uncommon",
        trigger_type="count_recovery",
        trigger_value="domme_saved",
    ),
    _a(
        "count_sub_blocked",
        "BOOOOOOOO!",
        "You got blocked from counting..",
        category="count",
        rarity="uncommon",
        trigger_type="count_blocked",
    ),
    _a(
        "count_domme_failed_recovery",
        "Happy Little Accident",
        "Oh well. Mistakes happen..",
        category="count",
        rarity="uncommon",
        trigger_type="count_recovery_expired",
        trigger_value="domme",
    ),
    _a(
        "count_last_second_save",
        "Last Second Legend",
        "You recovered the count with almost no time left. Rob’s tiny heart can’t take this.",
        category="count",
        rarity="rare",
        trigger_type="count_recovery",
        trigger_value="last_seconds",
    ),
    _a(
        "count_after_reset",
        "Back at One",
        "You restarted the count after a reset. A humble beginning.",
        category="count",
        rarity="common",
        trigger_type="count_after_reset",
    ),
    _a(
        "domme_first_tracked_send",
        "First Send Tracked",
        "Ooo, you got your first tracked send..",
        category="sends_domme",
        rarity="common",
        trigger_type="domme_total_cents",
        trigger_value=1,
    ),
    _a(
        "domme_first_test_send",
        "marie_123 Sent You AirPods",
        "Nice AirPods. Shame they’re not real..",
        category="sends_domme",
        rarity="common",
        trigger_type="test_send",
    ),
    _a(
        "domme_100_tracked",
        "Triple Digits",
        "You’ve had $100 in sends tracked by Rob..",
        category="sends_domme",
        rarity="common",
        trigger_type="domme_total_cents",
        trigger_value=10_000,
    ),
    _a(
        "domme_1000_tracked",
        "Rob Counts $1k Sends",
        "You’ve had $1k in sends tracked by Rob..",
        category="sends_domme",
        rarity="uncommon",
        trigger_type="domme_total_cents",
        trigger_value=100_000,
    ),
    _a(
        "domme_5000_tracked",
        "Big Number Behaviour",
        "You’ve had $5k in sends tracked by Rob. Rob is pretending to be normal about it.",
        category="sends_domme",
        rarity="rare",
        trigger_type="domme_total_cents",
        trigger_value=500_000,
    ),
    _a(
        "domme_top_10",
        "Top 10",
        "You entered the leaderboard top 10..",
        category="leaderboard",
        rarity="uncommon",
        trigger_type="domme_rank",
        trigger_value=10,
    ),
    _a(
        "domme_first_place",
        "This Is Yours",
        "You reached first place on the leaderboard..",
        category="leaderboard",
        rarity="rare",
        trigger_type="domme_rank",
        trigger_value=1,
    ),
    _a(
        "domme_regain_first",
        "The Comeback Crown",
        "You took first place back. Dramatic. Rob approves.",
        category="leaderboard",
        rarity="epic",
        trigger_type="domme_regain_first",
    ),
    _a(
        "domme_manual_send",
        "Cash App?? Never Heard of It",
        "You tracked a send manually..",
        category="sends_domme",
        rarity="common",
        trigger_type="manual_send",
    ),
    _a(
        "domme_10_sends_received",
        "Ten Little Notifications",
        "Rob has tracked 10 sends for you..",
        category="sends_domme",
        rarity="common",
        trigger_type="domme_send_count",
        trigger_value=10,
    ),
    _a(
        "domme_50_sends_received",
        "Notification Royalty",
        "Rob has tracked 50 sends for you. That’s a lot of pings.",
        category="sends_domme",
        rarity="rare",
        trigger_type="domme_send_count",
        trigger_value=50,
    ),
    _a(
        "domme_100_sends_received",
        "Send Magnet",
        "Rob has tracked 100 sends for you..",
        category="sends_domme",
        rarity="epic",
        trigger_type="domme_send_count",
        trigger_value=100,
    ),
    _a(
        "sub_first_send",
        "You Sent Some Money",
        "You sent your first tracked send..",
        category="sends_sub",
        rarity="common",
        trigger_type="sub_total_cents",
        trigger_value=1,
    ),
    _a(
        "sub_100_sent",
        "Triple Digit Tribute",
        "You’ve sent $100 tracked by Rob..",
        category="sends_sub",
        rarity="common",
        trigger_type="sub_total_cents",
        trigger_value=10_000,
    ),
    _a(
        "sub_1000_sent",
        "Welcome to the Thousand Club",
        "You’ve sent $1k to dommes in this server..",
        category="sends_sub",
        rarity="uncommon",
        trigger_type="sub_total_cents",
        trigger_value=100_000,
    ),
    _a(
        "sub_5000_sent",
        "Financially Committed",
        "You’ve sent $5k tracked by Rob. Rob is blinking slowly.",
        category="sends_sub",
        rarity="rare",
        trigger_type="sub_total_cents",
        trigger_value=500_000,
    ),
    _a(
        "sub_save_count",
        "Emergency Funds",
        "You sent during a count recovery window. Crisis averted.",
        category="sends_sub",
        rarity="uncommon",
        trigger_type="count_saved",
    ),
    _a(
        "sub_kingmaker",
        "Kingmaker",
        "Your send helped create a new leaderboard leader.",
        category="sends_sub",
        rarity="rare",
        trigger_type="kingmaker",
    ),
    _a(
        "sub_10_sends",
        "Frequent Flyer",
        "Rob has tracked 10 sends from you..",
        category="sends_sub",
        rarity="common",
        trigger_type="sub_send_count",
        trigger_value=10,
    ),
    _a(
        "sub_50_sends",
        "Repeat Customer",
        "Rob has tracked 50 sends from you..",
        category="sends_sub",
        rarity="rare",
        trigger_type="sub_send_count",
        trigger_value=50,
    ),
    _a(
        "sub_100_sends",
        "Loyalty Program",
        "Rob has tracked 100 sends from you. No points, just vibes.",
        category="sends_sub",
        rarity="epic",
        trigger_type="sub_send_count",
        trigger_value=100,
    ),
    _a(
        "throne_tracking_started",
        "Automation Station",
        "You enabled automatic Throne tracking. Rob is now professionally nosy.",
        category="throne_tracking",
        rarity="common",
        trigger_type="throne_tracking_started",
    ),
    _a(
        "throne_test_webhook",
        "Is This Thing On?",
        "Your Throne test webhook reached Rob successfully.",
        category="throne_tracking",
        rarity="common",
        trigger_type="throne_test_webhook",
    ),
    _a(
        "throne_first_real_auto_send",
        "The Machine Works",
        "Your first real automatic Throne send was tracked by Rob.",
        category="throne_tracking",
        rarity="uncommon",
        trigger_type="throne_first_real_auto_send",
    ),
    _a(
        "throne_optout",
        "Taking the Scenic Route",
        "You changed your tracking settings. Rob will try not to be dramatic about it.",
        category="throne_tracking",
        rarity="common",
        enabled=False,
        trigger_type="throne_optout",
    ),
    _a(
        "inactivity_returned_after_warning",
        "Back From the Void",
        "You returned after being marked as inactive. The void has been defeated.",
        category="inactivity",
        rarity="common",
        enabled=False,
        trigger_type="inactivity_returned",
    ),
    _a(
        "inactivity_final_warning_survivor",
        "Nearly a Ghost",
        "You came back just before Rob had to remove you. Dramatic timing.",
        category="inactivity",
        rarity="uncommon",
        enabled=False,
        trigger_type="inactivity_final_return",
    ),
    _a(
        "rejoined_vib",
        "The Return",
        "You came back to VIB. Rob is happy now!",
        category="inactivity",
        rarity="rare",
        enabled=False,
        trigger_type="rejoined_vib",
    ),
    _a(
        "maintenance_survivor",
        "I Was There",
        "You used Rob during one of his “briefly held together with duct tape” eras.",
        category="maintenance",
        rarity="uncommon",
        enabled=False,
        trigger_type="maintenance_interaction",
    ),
    _a(
        "leaderboard_during_maintenance",
        "Refreshing the Void",
        "You checked the leaderboard while Rob was under maintenance. Optimistic.",
        category="maintenance",
        rarity="common",
        enabled=False,
        trigger_type="maintenance_leaderboard_view",
    ),
    _a(
        "first_achievement_view",
        "Trophy Cabinet",
        "You checked your achievements. Very humble of you.",
        category="misc",
        rarity="common",
        trigger_type="achievements_view",
    ),
    _a(
        "viewed_other_achievements",
        "Nosy Little Thing",
        "You checked someone else’s achievements. Rob saw that.",
        category="misc",
        rarity="common",
        trigger_type="achievements_view_other",
    ),
    _a(
        "dm_rob",
        "Did Rob Ghost You?",
        "You messaged Rob. I guess that's achievement worth.",
        category="misc",
        rarity="common",
        trigger_type="dm_rob",
    ),
    _a(
        "secret_command",
        "Shhhh...",
        "I’ll give you an achievement as long as we never speak of this again. Got it?",
        category="secret",
        rarity="secret",
        hidden=True,
        enabled=True,
        trigger_type="secret_command",
    ),
)


ACHIEVEMENTS_BY_KEY = {achievement.key: achievement for achievement in ACHIEVEMENTS}
ENABLED_ACHIEVEMENTS = tuple(achievement for achievement in ACHIEVEMENTS if achievement.enabled)
TOTAL_ACHIEVEMENT_COUNT = len(ENABLED_ACHIEVEMENTS)


def achievements_by_category(
    achievements: list[AchievementDefinition] | tuple[AchievementDefinition, ...],
) -> dict[AchievementCategory, list[AchievementDefinition]]:
    """Group a list of achievements by their category, preserving order."""
    grouped: dict[AchievementCategory, list[AchievementDefinition]] = {}
    for achievement in achievements:
        grouped.setdefault(achievement.category, []).append(achievement)
    return grouped


def sort_by_rarity(
    achievements: list[AchievementDefinition],
    *,
    reverse: bool = False,
) -> list[AchievementDefinition]:
    """Sort achievements by rarity (common first by default)."""
    return sorted(achievements, key=lambda a: a.rarity_rank, reverse=reverse)
