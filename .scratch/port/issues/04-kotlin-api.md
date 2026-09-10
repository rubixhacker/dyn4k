# Choose the idiomatic Kotlin API and shim boundary

Id: 04
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Status: open
Assignee: none
Blocked by: 03

## Question

What Kotlin API conventions and ownership/mutability model should dyn4k expose, and what adapter boundary preserves all baseline extension and migration contracts with a thin shim? Choose the boundary with concrete baseline examples; decide which uncertainties need a throwaway prototype before committing to the design.

## Comments

Created during initial map charting. Requires live user discussion before resolution.


Research input: [Shim feasibility](../../../docs/research/shim.md). Discuss one canonical mutable model with two API surfaces versus shared algorithms behind explicit model contracts. Neither is approved. Use the concrete retained-velocity field-write, protected-state subclass, custom-world override, and solver/listener identity journeys to choose a prototype. Ordinary forwarding or Kotlin type aliases alone are not a proven solution.
