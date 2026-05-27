"""Règles de gestion du risque Topstep 150k Combine / Express Funded.

Référence: https://www.topstep.com/ (à vérifier régulièrement, les règles évoluent).

Règles modélisées:
- Solde de départ: $150,000
- Trailing Max Drawdown: $5,000 (calculé sur le plus haut de l'EOD balance)
- Daily Loss Limit: $3,000 (réinitialisé à minuit CT)
- Profit Target (Combine): $9,000
- Consistency rule (Express Funded): aucune journée ne doit représenter > 50% du profit total
"""

from dataclasses import dataclass, field
import datetime as dt


@dataclass
class TopstepAccount:
    starting_balance: float = 150_000.0
    max_drawdown: float = 5_000.0
    daily_loss_limit: float = 3_000.0
    profit_target: float = 9_000.0

    balance: float = field(init=False)
    high_water_mark: float = field(init=False)
    trailing_threshold: float = field(init=False)
    daily_pnl: float = 0.0
    current_day: dt.date | None = None
    violated: str | None = None

    def __post_init__(self):
        self.balance = self.starting_balance
        self.high_water_mark = self.starting_balance
        self.trailing_threshold = self.starting_balance - self.max_drawdown

    def on_new_day(self, day: dt.date):
        if self.current_day is None or day != self.current_day:
            self.current_day = day
            self.daily_pnl = 0.0

    def apply_pnl(self, pnl: float, ts: dt.datetime) -> bool:
        """Applique un PnL, met à jour les seuils. Retourne True si le compte est encore valide."""
        if self.violated:
            return False
        self.on_new_day(ts.date())
        self.balance += pnl
        self.daily_pnl += pnl

        if self.balance > self.high_water_mark:
            self.high_water_mark = self.balance
            new_threshold = self.high_water_mark - self.max_drawdown
            self.trailing_threshold = min(
                max(self.trailing_threshold, new_threshold),
                self.starting_balance,
            )

        if self.daily_pnl <= -self.daily_loss_limit:
            self.violated = "daily_loss_limit"
            return False
        if self.balance <= self.trailing_threshold:
            self.violated = "max_drawdown"
            return False
        return True

    def hit_profit_target(self) -> bool:
        return self.balance - self.starting_balance >= self.profit_target
