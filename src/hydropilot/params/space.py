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
        seenIdentities = set()
        types: List[int] = []
        ubs: List[float] = []
        lbs: List[float] = []
        sets: Dict[int, List[float]] = {}

        nameCounts: Dict[str, int] = {}
        for spec in design_list:
            nameCounts[spec.name] = nameCounts.get(spec.name, 0) + 1
        for i, spec in enumerate(design_list):
            if nameCounts[spec.name] > 1 and spec.scope is None:
                raise ValueError(f"scope is required for repeated design parameter name '{spec.name}'")
            identity = (spec.name, spec.scope)
            if identity in seenIdentities:
                raise ValueError(f"Duplicate design parameter identity: {spec.label}")
            seenIdentities.add(identity)
            if spec.label in seen_names:
                raise ValueError(f"Conflicting design parameter labels: {spec.label}")
            seen_names.add(spec.label)
            names.append(spec.label)
            types.append(spec.typeCode)
            if spec.type == "discrete":
                sets[i] = spec.sets
            lbs.append(spec.lb)
            ubs.append(spec.ub)

        return len(names), names, types, sets, ubs, lbs

    def get_param_info(self):
        return self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb
