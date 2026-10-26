"""Budgeted parameter selection around the unchanged Steps 1–6 services.

Validation receives only dated historical blocks. Candidate construction, score
calculation and deterministic ranking do not consume outer-test results.
"""
from dataclasses import asdict
from itertools import product
from math import isfinite
from random import Random
from statistics import median
import hashlib
import json

from .backtesting import (TestPeriod, aggregate_portfolio, audit_prefix, audit_result,
                          prepare_block, simulate_block)
from .breakouts import BreakoutSettings
from .methods import create_method
from .trading import TradeSettings
from .trendlines import TrendSettings


def canonical(value):
    """Stable JSON for configuration IDs, de-duplication and input hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_id(config):
    """Identify all effective settings, independently of trial order or stage."""
    return hashlib.sha256(canonical(config).encode()).hexdigest()[:16]


def make_config(method, attributes=None, trend=None, breakout=None, trade=None):
    """Expand defaults into explicit validated dataclass attributes.

    Costs live in the experiment scenarios, not in the search space. Position
    sizing and next-session execution remain fixed for a fair comparison.
    """
    strategy = create_method(method, **(attributes or {}))
    trade = TradeSettings(**(trade or {"entry_timing": "next_open"}))
    if strategy.basis != "close" or not trade.enabled or trade.entry_timing != "next_open":
        raise ValueError("Parameter selection requires Close signals and next_open fills")
    return dict(method=dict(name=method, attributes=asdict(strategy.settings)),
                trend=asdict(TrendSettings(**(trend or {}))),
                breakout=asdict(BreakoutSettings(**(breakout or {}))), trade=asdict(trade))


def check_config(config):
    """Reject unknown fields and validate a portable selected configuration."""
    if set(config) != {"method", "trend", "breakout", "trade"} or set(config["method"]) != {"name", "attributes"}:
        raise ValueError("Invalid selected configuration schema")
    return make_config(config["method"]["name"], config["method"]["attributes"],
                       config["trend"], config["breakout"], config["trade"])


def default_config(plan, method):
    """Application default signal settings under the common backtest accounting."""
    return make_config(method, trend=plan["trend_settings"], breakout=plan["breakout_settings"],
                       trade=plan["trade_settings"])


def swing_candidates(plan, method):
    """Stage 1: the declared small grid for one swing-sensitivity attribute."""
    spec = plan["swing_grids"][method]
    return [make_config(method, {spec["attribute"]: value}, plan["trend_settings"],
                        plan["breakout_settings"], plan["trade_settings"]) for value in spec["values"]]


def joint_candidates(plan, method, parent, round_index, excluded):
    """Stage 2: seeded sampling without replacement from the joint finite grid.

    Retain the Stage 1 swing attributes; vary tolerance, consecutive-close
    confirmation, ATR stop distance and reward/risk together. Excluded IDs avoid
    spending a second trial on a configuration already evaluated in Stage 1.
    """
    space = plan["joint_space"]
    keys = ("tolerance_percent", "confirmation_bars", "atr_stop_multiple", "reward_risk_multiple")
    combinations = list(product(*(space[k] for k in keys)))
    seed_text = f"{plan['seed']}:{round_index}:{method}"
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:16], 16)
    Random(seed).shuffle(combinations)
    result, seen = [], set(excluded)
    for tolerance, confirmation, stop, target in combinations:
        config = make_config(method, parent["method"]["attributes"],
                             {**parent["trend"], "tolerance_percent": tolerance},
                             {**parent["breakout"], "confirmation_bars": confirmation},
                             {**parent["trade"], "atr_stop_multiple": stop, "reward_risk_multiple": target})
        identity = config_id(config)
        if identity not in seen:
            result.append(config)
            seen.add(identity)
        if len(result) == plan["joint_trials_per_method"]:
            return result
    raise ValueError("Joint trial budget exceeds the distinct available configurations")


def score_blocks(blocks, constraints):
    """Rank robust net returns, subject to predeclared trade-count/drawdown gates.

    Each row is one equal-duration validation block's summed stock portfolio.
    Median return is in percentage points, not annualised. Marked open P/L is
    included. Summed P/L describes independent block resets, not compounding.
    """
    if not blocks:
        raise ValueError("Cannot score zero blocks")
    returns = [b["account_return_percent"] for b in blocks]
    if any(not isfinite(v) for v in returns):
        raise ValueError("Nonfinite validation return")
    closed = sum(b["closed_trades"] for b in blocks)
    worst = max(b["max_drawdown_percent"] for b in blocks)
    reasons = []
    if len(blocks) < constraints["minimum_blocks"]:
        reasons.append("too_few_blocks")
    if closed < constraints["minimum_closed_trades"]:
        reasons.append("too_few_closed_trades")
    if min(b["closed_trades"] for b in blocks) < constraints["minimum_closed_per_block"]:
        reasons.append("too_few_closed_in_a_block")
    if worst > constraints["maximum_drawdown_percent"]:
        reasons.append("drawdown_limit")
    return dict(eligible=not reasons, constraint_failures=reasons,
                median_return_percent=median(returns),
                aggregate_net_pnl=sum(b["net_pnl"] for b in blocks),
                worst_drawdown_percent=worst, closed_trades=closed,
                positive_blocks=sum(v > 0 for v in returns), validation_blocks=len(blocks))


def choose_best(trials, require_eligible=True):
    """Highest median, then lower drawdown, higher summed P/L, then stable ID.

    Return None if no completed eligible trial exists. An ineligible Stage 1
    seed may be used for exploration only; the final selection still applies
    all constraints and explicitly falls back to the baseline if necessary.
    """
    valid = [t for t in trials if t["status"] == "completed" and
             (t["eligible"] or not require_eligible)]
    return min(valid, key=lambda t: (-t["median_return_percent"], t["worst_drawdown_percent"],
                                    -t["aggregate_net_pnl"], t["config_id"])) if valid else None


def validate_plan(plan):
    """Fail before fitting on invalid dates, overlapping universes or search keys."""
    required = {"version", "data_dir", "development_symbols", "heldout_symbols", "rounds",
                "minimum_warmup_bars", "seed", "swing_grids", "joint_space", "joint_trials_per_method",
                "constraints", "trend_settings", "breakout_settings", "trade_settings", "cost_scenarios",
                "selection_scenario", "prefix_audit_symbols"}
    if set(plan) != required or plan["version"] != 1:
        raise ValueError("Unsupported parameter-search plan schema")
    for key in ("development_symbols", "heldout_symbols"):
        values = plan[key]
        if not values or len(values) != len(set(values)) or any(not isinstance(s, str) or not s or
                not all(c.isalnum() or c in "_-" for c in s) for s in values):
            raise ValueError("Symbols must be unique safe identifiers")
    if set(plan["development_symbols"]) & set(plan["heldout_symbols"]):
        raise ValueError("Held-out symbols must never belong to the selection universe")
    if not set(plan["prefix_audit_symbols"]) <= set(plan["development_symbols"] + plan["heldout_symbols"]):
        raise ValueError("Unknown prefix-audit symbol")
    for key, minimum in (("minimum_warmup_bars", 0), ("seed", 0), ("joint_trials_per_method", 1)):
        if isinstance(plan[key], bool) or not isinstance(plan[key], int) or plan[key] < minimum:
            raise ValueError(f"Invalid {key}")
    limits = plan["constraints"]
    if set(limits) != {"minimum_blocks", "minimum_closed_trades", "minimum_closed_per_block", "maximum_drawdown_percent"}:
        raise ValueError("Unexpected constraints")
    for key in ("minimum_blocks", "minimum_closed_trades", "minimum_closed_per_block"):
        if isinstance(limits[key], bool) or not isinstance(limits[key], int) or limits[key] < 1:
            raise ValueError("Trade-count and block-count constraints must be positive integers")
    if not isinstance(limits["maximum_drawdown_percent"], (int, float)) or isinstance(limits["maximum_drawdown_percent"], bool) or not 0 < limits["maximum_drawdown_percent"] <= 100:
        raise ValueError("Invalid drawdown constraint")
    rounds = plan["rounds"]
    if not rounds or len({r["name"] for r in rounds}) != len(rounds):
        raise ValueError("Provide unique walk-forward rounds")
    previous_test = None
    for row in rounds:
        if set(row) != {"name", "validation", "test"} or not row["name"] or not all(c.isalnum() or c in "_-" for c in row["name"]):
            raise ValueError("Invalid round")
        periods = [TestPeriod(**p) for p in row["validation"]]
        test = TestPeriod(**row["test"])
        if len(periods) < limits["minimum_blocks"] or len({p.name for p in periods}) != len(periods):
            raise ValueError("Insufficient or duplicate validation blocks")
        for earlier, later in zip(periods, periods[1:]):
            if earlier.end >= later.start:
                raise ValueError("Validation blocks must be chronological and disjoint")
        if periods[-1].end >= test.start:
            raise ValueError("Outer test must follow every validation block")
        if previous_test is not None and previous_test.end >= test.start:
            raise ValueError("Outer tests must be chronological and disjoint")
        previous_test = test
        # Avoid a long block outweighing a short one in the median score.
        from datetime import date
        lengths = [(date.fromisoformat(p.end)-date.fromisoformat(p.start)).days+1 for p in periods]
        if max(lengths)-min(lengths) > 7:
            raise ValueError("Validation blocks must have approximately equal calendar durations")
    expected = {"ta": "window", "percentage": "reversal_percent", "atr": "atr_multiplier",
                "prominence": "min_prominence_percent"}
    grids = plan["swing_grids"]
    if not grids or not set(grids) <= set(expected) or "ta" not in grids:
        raise ValueError("Search requires TA and supported swing strategies")
    for method, spec in grids.items():
        if set(spec) != {"attribute", "values"} or spec["attribute"] != expected[method] or not spec["values"]:
            raise ValueError("Invalid swing grid")
        configs = swing_candidates(plan, method)
        if len({config_id(c) for c in configs}) != len(configs):
            raise ValueError("Duplicate swing-grid values")
    space = plan["joint_space"]
    if set(space) != {"tolerance_percent", "confirmation_bars", "atr_stop_multiple", "reward_risk_multiple"}:
        raise ValueError("Unexpected joint search dimensions")
    for key, values in space.items():
        if not values or len(values) != len(set(values)):
            raise ValueError("Joint ranges must be nonempty and distinct")
        for value in values:
            if key == "tolerance_percent": TrendSettings(**{**plan["trend_settings"], key: value})
            elif key == "confirmation_bars": BreakoutSettings(**{**plan["breakout_settings"], key: value})
            else: TradeSettings(**{**plan["trade_settings"], key: value})
    costs = plan["cost_scenarios"]
    if not costs or plan["selection_scenario"] not in costs:
        raise ValueError("Selection cost scenario is missing")
    for name, cost in costs.items():
        if set(cost) != {"slippage_bps", "fee_per_order", "short_borrow_rate_percent"} or not name or not all(c.isalnum() or c in "_-" for c in name):
            raise ValueError("Invalid cost scenario")
        TradeSettings(**{**plan["trade_settings"], **cost})
    for method in grids:
        parent = default_config(plan, method)
        joint_candidates(plan, method, parent, 0, {config_id(c) for c in swing_candidates(plan, method)})
    return plan


_DATA = {}


def init_worker(data):
    """Process initializer: read-only price histories for this declared universe."""
    global _DATA
    _DATA = data


def evaluate_job(task):
    """Evaluate candidates for one stock/block; reuse identical Steps 1–4 replays.

    Args:
        task: Symbol, dated block, effective configurations and cost scenario.
    Returns:
        Per-configuration metrics and paths; optionally audited trade ledgers.
    A failed configuration remains in the result, never silently disappears.
    """
    symbol, period, configs, cost_name, costs, warmup, detail, prefix_check = task
    period = TestPeriod(**period)
    cache, outputs = {}, []
    for config in configs:
        identity = config_id(config)
        try:
            key = canonical({k: config[k] for k in ("method", "trend", "breakout")})
            if key not in cache:
                method = create_method(config["method"]["name"], **config["method"]["attributes"])
                cache[key] = prepare_block(_DATA[symbol], period, method, TrendSettings(**config["trend"]),
                                           BreakoutSettings(**config["breakout"]), warmup)
            block = cache[key]
            settings = TradeSettings(**{**config["trade"], **costs})
            result, summary, equity, bh = simulate_block(block, settings, symbol, cost_name)
            # Unique portfolio arm is attached by the coordinator, not the engine.
            summary.update(config_id=identity,
                           long_net_pnl=sum(t.net_pnl if t.exit_index is not None else t.unrealized_pnl
                                            for t in result.trades if t.side == "long"),
                           short_net_pnl=sum(t.net_pnl if t.exit_index is not None else t.unrealized_pnl
                                             for t in result.trades if t.side == "short"))
            item = dict(status="completed", config_id=identity, summary=summary,
                        equity=[r["equity"] for r in equity], benchmark=[r["equity"] for r in bh],
                        timestamps=[r["timestamp"] for r in equity])
            if detail:
                item["audit"] = audit_result(block.bars, block.start_index, result, summary)
                item["trades"] = [t.as_record(block.bars) for t in result.trades]
                if prefix_check:
                    item["prefix_audit"] = audit_prefix(block, settings, result)
            outputs.append(item)
        except Exception as error:
            outputs.append(dict(status="failed", config_id=identity, symbol=symbol,
                                period=period.name, error=f"{type(error).__name__}: {error}"))
    return outputs


def aggregate_items(items):
    """Reconstruct aligned portfolio paths and expose stock-bar exposure."""
    summaries = [x["summary"] for x in items]
    equities, benchmarks = {}, {}
    for item in items:
        symbol = item["summary"]["symbol"]
        equities[symbol] = [dict(timestamp=t, equity=e) for t, e in zip(item["timestamps"], item["equity"])]
        benchmarks[symbol] = [dict(timestamp=t, equity=e) for t, e in zip(item["timestamps"], item["benchmark"])]
    total, curve = aggregate_portfolio(summaries, equities, benchmarks)
    total.update(config_id=items[0]["config_id"],
                 long_net_pnl=sum(s["long_net_pnl"] for s in summaries),
                 short_net_pnl=sum(s["short_net_pnl"] for s in summaries),
                 exposure_percent=100*sum(s["bars_with_position_at_close"] for s in summaries)/sum(s["test_bars"] for s in summaries))
    return total, curve
