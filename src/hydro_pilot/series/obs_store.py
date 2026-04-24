from ..io.readers.dispatcher import read_extract


class ObsStore:
    def __init__(self, series_plan):
        self.series_plan = series_plan
        self.obs_data = self._load_obs()

    def _load_obs(self):
        obs_data = {}
        for sid, item in self.series_plan.items.items():
            obs_item = item["obsItem"]
            obs_data[sid] = read_extract(None, obs_item) if obs_item is not None else None
        return obs_data

    def get(self, sid: str):
        return self.obs_data.get(sid)
