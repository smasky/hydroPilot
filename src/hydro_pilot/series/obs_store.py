from ..io.readers.dispatcher import read_extract


class ObsStore:
    def __init__(self, series_plan):
        self.series_plan = series_plan
        self.obs_data = self._load_obs()

    def _load_obs(self):
        return {
            sid: read_extract(None, item.obs) if item.obs is not None else None
            for sid, item in self.series_plan.seriesItems.items()
        }

    def get(self, sid: str):
        return self.obs_data.get(sid)
