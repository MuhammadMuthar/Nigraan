"""Process-wide state: models loaded once at startup, cached scoring context keyed by a data version."""
from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Customer, Receivable
from app.services.ledger import Ledger
from app.services.receivables.late_model import MIN_HISTORY, predict as late_predict, receivable_features, top_late_reasons
from app.services.scoring.risk import ModelBundle
from app.services.scoring.scorer import Scorer, ScoringContext


class Runtime:
    def __init__(self):
        self.lock = threading.RLock()
        self.version = 0
        self.bundle = ModelBundle()
        self.scorer = Scorer(self.bundle)
        self.models_path: Path | None = None
        self._ctx: ScoringContext | None = None
        self._ctx_version = -1
        self._late: dict | None = None
        self._late_version = -1

    def load_models(self, path: Path | None = None) -> None:
        with self.lock:
            p = path or get_settings().models_dir
            self.bundle = ModelBundle.load(p)
            self.scorer = Scorer(self.bundle)
            self.models_path = p
            self.bump()

    def bump(self) -> None:
        with self.lock:
            self.version += 1

    def scoring_context(self, db: Session) -> ScoringContext:
        with self.lock:
            if self._ctx is None or self._ctx_version != self.version:
                self._ctx = self.scorer.prepare(Ledger.from_db(db))
                self._ctx_version = self.version
            return self._ctx

    def receivable_frames(self, db: Session) -> tuple[pd.DataFrame, pd.DataFrame]:
        cols = [Receivable.id, Receivable.customer_id, Receivable.invoice_no, Receivable.issue_date, Receivable.due_date,
                Receivable.terms_days, Receivable.amount, Receivable.paid_date, Receivable.paid_amount,
                Receivable.disputed_amount]
        r = pd.DataFrame(db.execute(select(*cols)).all(), columns=[c.key for c in cols])
        ccols = [Customer.id, Customer.name, Customer.city, Customer.segment, Customer.terms_days, Customer.created_at]
        c = pd.DataFrame(db.execute(select(*ccols)).all(), columns=[x.key for x in ccols])
        return r, c

    def late_risk(self, db: Session) -> dict:
        """Late-payment risk for every open receivable (prediction moment: issue date)."""
        with self.lock:
            if self._late is not None and self._late_version == self.version:
                return self._late
            r, c = self.receivable_frames(db)
            open_r = r[r["paid_date"].isna()]
            out: dict[int, dict] = {}
            late = self.bundle.late
            if late is not None and not open_r.empty:
                X = receivable_features(r, c)
                Xo = X.loc[open_r["id"].astype(int).values]
                p, contrib = late_predict(late, Xo)
                seg = c.set_index("id")["segment"].to_dict()
                rates = late.get("segment_rates", {})
                for i, rid in enumerate(Xo.index):
                    feats = Xo.loc[rid].to_dict()
                    limited = feats["prior_settled"] < MIN_HISTORY
                    cust = int(open_r.set_index("id").loc[rid, "customer_id"])
                    risk = float(rates.get(seg.get(cust), late["base_rate"])) if limited else float(p[i])
                    out[int(rid)] = {
                        "risk": risk, "model_risk": float(p[i]), "limited_history": bool(limited),
                        "reasons": ([f"Limited history ({int(feats['prior_settled'])} settled invoices): "
                                     f"showing the {seg.get(cust, 'segment')} segment average"] if limited else
                                    top_late_reasons(None if contrib is None else contrib[i], feats)),
                        "settled": int(feats["prior_settled"]),
                    }
            self._late = {"by_id": out, "kind": late["kind"] if late else None,
                          "label": late.get("output_label", "late-payment risk") if late else None}
            self._late_version = self.version
            return self._late


runtime = Runtime()
