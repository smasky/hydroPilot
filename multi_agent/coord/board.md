# Board

## Current Goal

- Sol filter reinstated. All tasks complete.

## Final Support Matrix

| Group | Filter Keys | Status | Basis |
|-------|------------|--------|-------|
| bsn | none | Global (OBJ_TOT=0) | FORTRAN: case("bsn") → num_elem=1 |
| hru | object_id, lu_mgt, soil, hydro_name | Implemented | T-059 |
| sol | soil (exact match) | **Reinstated (T-075)** | FORTRAN: case("sol") → sp_ob%hru (HRU IDs) |
| cha | object_id | Implemented | T-070 |
