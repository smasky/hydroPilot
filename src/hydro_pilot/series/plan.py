from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SeriesPlanItem:
    id: str
    sim: Any
    obs: Any


class SeriesPlan:
    def __init__(self, series_list):
        self.seriesItems: dict[str, SeriesPlanItem] = self._build_series_items(series_list)

    def _build_series_items(self, series_list) -> dict[str, SeriesPlanItem]:
        return {
            series.id: SeriesPlanItem(
                id=series.id,
                sim=series.sim,
                obs=series.obs,
            )
            for series in series_list
        }
