"""Comparable direction-adjusted scores, frozen when a trend earns entry."""
def rank_group(candidates):
    return tuple(sorted(candidates,key=lambda r:(-r.strength,r.crossover_time,r.symbol,r.key)))
