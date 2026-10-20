"""MOD-NIOKR: EVM (освоенный объем) и PERT-оценка сроков — алгоритмы, апробированные
в прототипе v8 (заимствованы из прототипа-аналога АС «НИОКР-Сопровождение» v23).

EVM:  PV = budget × (stage+1)/9 · EV = budget × (stage + 0.5·[gate=go]) / 9
      AC = EV × (0.92 + risk_idx/400) · SPI = EV/PV · CPI = EV/AC
PERT: te = (o + 4m + p)/6 · σ = (p − o)/6 · P(уложиться) = Φ((days_left − te)/σ)
"""
from __future__ import annotations

import math

from ..models import Organization, Project


def evm(project: Project, org: Organization) -> dict:
    done_share = min(1.0, (project.lc_stage + (0.5 if project.gate == "go" else 0.0)) / 9.0)
    plan_share = min(1.0, (project.lc_stage + 1) / 9.0)
    pv = round(project.budget * plan_share, 2)
    ev = round(project.budget * done_share, 2)
    ac = round(ev * (0.92 + org.risk_idx / 400.0), 2)
    spi = round(ev / pv, 2) if pv > 0 else 0.0
    cpi = round(ev / ac, 2) if ac > 0 else 0.0
    return {"pv": pv, "ev": ev, "ac": ac, "spi": spi, "cpi": cpi,
            "spi_status": "в графике" if spi >= 1 else ("риск" if spi >= 0.85 else "отставание"),
            "cpi_status": "в бюджете" if cpi >= 1 else ("риск" if cpi >= 0.85 else "перерасход")}


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def pert(project: Project, days_left: int) -> dict:
    o, m, p = project.pert_o, project.pert_m, project.pert_p
    te = round((o + 4 * m + p) / 6.0, 1)
    sd = round((p - o) / 6.0, 1)
    z = (days_left - te) / sd if sd > 0 else 0.0
    return {"o": o, "m": m, "p": p, "te": te, "sd": sd, "days_left": days_left,
            "probability": round(norm_cdf(z) * 100)}


def portfolio_evm(pairs: list[tuple[Project, Organization]]) -> dict:
    """Агрегаты портфеля: ΣEV/ΣPV, ΣEV/ΣAC + антирейтинг SPI."""
    if not pairs:
        return {"spi": 0, "cpi": 0, "worst": None}
    evs = [evm(p, o) for p, o in pairs]
    s_pv = sum(e["pv"] for e in evs) or 1e-9
    s_ev = sum(e["ev"] for e in evs)
    s_ac = sum(e["ac"] for e in evs) or 1e-9
    worst_i = min(range(len(evs)), key=lambda i: evs[i]["spi"])
    return {"spi": round(s_ev / s_pv, 2), "cpi": round(s_ev / s_ac, 2),
            "totals": {"pv": round(s_pv, 2), "ev": round(s_ev, 2), "ac": round(s_ac, 2)},
            "worst": {"project": pairs[worst_i][0].id, "spi": evs[worst_i]["spi"]},
            "by_project": {pairs[i][0].id: evs[i] for i in range(len(evs))}}
