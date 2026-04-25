from typing import Dict, List, Tuple


class ParamSpace:
    def __init__(self, design_list):
        self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb = (
            self._build_space(design_list)
        )

    def _build_space(
        self, design_list
    ) -> Tuple[int, List[str], List[int], Dict[int, List[float]], List[float], List[float]]:
        names: List[str] = []
        seen_names = set()
        types: List[int] = []
        ubs: List[float] = []
        lbs: List[float] = []
        sets: Dict[int, List[float]] = {}

        for i, spec in enumerate(design_list):
            if spec.name in seen_names:
                raise ValueError(f"Duplicate design parameter name: {spec.name}")
            seen_names.add(spec.name)
            names.append(spec.name)
            types.append(spec.typeCode)
            if spec.type == "discrete":
                sets[i] = spec.sets
            lbs.append(spec.lb)
            ubs.append(spec.ub)

        return len(names), names, types, sets, ubs, lbs

    def get_param_info(self):
        return self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb
