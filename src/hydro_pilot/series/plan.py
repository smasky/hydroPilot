class SeriesPlan:
    def __init__(self, series_list):
        self.items = self._build_items(series_list)

    def _build_items(self, series_list):
        items = {}
        for s in series_list:
            items[s.id] = {
                "id": s.id,
                "simItem": s.sim,
                "obsItem": s.obs,
            }
        return items
