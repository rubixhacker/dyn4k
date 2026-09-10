# Define numerical and migration acceptance

Id: 06
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Status: open
Assignee: none
Blocked by: 01, 03

## Question

Which baseline tests, unchanged Java consumer builds, extension-point scenarios and cross-target simulation fixtures establish full functionality and source compatibility? Choose tolerances and evaluation metrics by scenario, including long-running simulations, callback order, error semantics and mutable-object behavior; decide how baseline bugs are handled without silently changing the fixed compatibility contract.

## Comments

Created during initial map charting. Requires live user discussion before resolution.


Research inputs: [Pinned baseline](../../../docs/research/baseline.md) and [Shim constraints](../../../docs/research/shim.md). Include an exhaustive public/protected declaration inventory and unchanged Java consumer corpus in acceptance planning. Include runtime class-based filters, exact-class copying, collection views, user-data identity and platform numerical/bit-operation behavior; package counts or a few smoke fixtures cannot establish full compatibility.
