import copy
from typing import Any, Dict, List, Optional


DEFAULT_MODE = "v"


def auto_physical(
    designItem: Dict[str, Any],
    paramDb: Dict[str, Any],
    *,
    modelName: str,
) -> Dict[str, Any]:
    name = designItem["name"]
    dbEntry = paramDb.get(name)
    if not dbEntry:
        raise ValueError(
            f"Unknown {modelName} parameter '{name}': not found in the {modelName} parameter database and no inline location provided."
        )
    return {
        "name": name,
        "type": designItem.get("type", dbEntry["type"]),
        "mode": DEFAULT_MODE,
        "bounds": designItem.get("bounds", dbEntry.get("bounds")),
        "filter": None,
        "location": copy.deepcopy(dbEntry["file"]),
    }


def merge_physical(
    designItem: Optional[Dict[str, Any]],
    physItem: Dict[str, Any],
    paramDb: Dict[str, Any],
    *,
    modelName: str,
) -> Dict[str, Any]:
    name = physItem["name"]
    dbEntry = paramDb.get(name)

    location = physItem.get("location")
    if not location:
        if dbEntry:
            location = copy.deepcopy(dbEntry["file"])
        else:
            raise ValueError(
                f"Parameter '{name}' has no inline location and is not in the {modelName} parameter database."
            )

    paramType = physItem.get("type")
    if not paramType:
        paramType = dbEntry["type"] if dbEntry else "float"

    if designItem and "bounds" in designItem:
        bounds = designItem["bounds"]
    elif "bounds" in physItem:
        bounds = physItem["bounds"]
    elif dbEntry and "bounds" in dbEntry:
        bounds = dbEntry["bounds"]
    else:
        bounds = None

    return {
        "name": name,
        "type": paramType,
        "mode": physItem.get("mode", DEFAULT_MODE),
        "bounds": bounds,
        "filter": physItem.get("filter"),
        "location": location,
    }


def resolve_physical_params(
    design: List[Dict[str, Any]],
    physical: Optional[List[Dict[str, Any]]],
    transformer: Optional[str],
    paramDb: Dict[str, Any],
    *,
    modelName: str,
) -> List[Dict[str, Any]]:
    if physical is None:
        return [auto_physical(d, paramDb, modelName=modelName) for d in design]

    if transformer is None:
        physByName: Dict[str, List[Dict[str, Any]]] = {}
        for p in physical:
            physByName.setdefault(p["name"], []).append(p)

        result = []
        for d in design:
            pList = physByName.get(d["name"])
            if not pList:
                result.append(auto_physical(d, paramDb, modelName=modelName))
            else:
                for p in pList:
                    result.append(merge_physical(d, p, paramDb, modelName=modelName))
        return result

    return [
        merge_physical(None, p, paramDb, modelName=modelName)
        for p in physical
    ]


def build_design_items(
    design: List[Dict[str, Any]],
    paramDb: Dict[str, Any],
    *,
    modelName: str,
) -> List[Dict[str, Any]]:
    designItems = []
    for d in design:
        name = d["name"]
        dbEntry = paramDb.get(name)
        item = {"name": name, "type": d.get("type", dbEntry["type"] if dbEntry else "float")}
        if "bounds" in d:
            item["bounds"] = d["bounds"]
        elif dbEntry and "bounds" in dbEntry:
            item["bounds"] = dbEntry["bounds"]
        else:
            raise ValueError(f"Parameter '{name}' has no bounds")
        if d.get("sets"):
            item["sets"] = d["sets"]
        designItems.append(item)
    return designItems
