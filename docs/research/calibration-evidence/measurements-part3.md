# Baseline diagnostic measurements

No numerical limits or invariant acceptance are established by this report.

Cases: 227. Reference catalog: 909. Partition: 3/4 (zero-based). Matched trajectory comparisons: 209. Missing references: 0.

## Coverage gaps

- C-stack-s0.01-o1000.0,1000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz60: [no solved contact callbacks]
- C-stack-s1.0-o0.0,0.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s1.0-o0.0,0.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o0.0,0.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz60: [no solved contact callbacks]
- C-stack-s1.0-o1000000.0,-1000000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o0.0,0.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz60: [no solved contact callbacks]
- C-stack-s100.0-o-1000.0,1000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz60: [no solved contact callbacks]

## Largest normalized trajectory differences

Differences are componentwise maxima at common physical times, not acceptance failures. Values are normalized to nominal length/mass units. See JSON for every component maximum and the first differing sample.

| Case | Comparison | Largest difference | Quantity | Time (s) |
| --- | --- | ---: | --- | ---: |
| C-bounce-e0.0-s0.01-o0.0,0.0-hz30 | scale/origin | 0.00358818367713207 | b1.position.x | 0.6 |
| C-bounce-e0.0-s0.01-o0.0,0.0-hz30 | timestep | 5.553333333333335 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s0.01-o0.0,0.0-hz30 | scale/origin | 0.00500390554821388 | b1.position.y | 0.03333333333333333 |
| CCD-world-circle-ALL-s0.01-o0.0,0.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s0.01-o0.0,0.0-hz30 | scale/origin | 2.2737367544323206E-13 | j0.reactionForce.y | 0.1 |
| L-spring-damperfalse-s0.01-o0.0,0.0-hz30 | timestep | 395.6843085580123 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s0.01-o0.0,0.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s0.01-o0.0,0.0-hz60 | scale/origin | 5.270380790304731E-11 | b1.position.x | 0.016666666666666666 |
| C-bounce-e0.0-s0.01-o0.0,0.0-hz120 | scale/origin | 0.003588183677045123 | b1.position.x | 0.5583333333333333 |
| C-bounce-e0.0-s0.01-o0.0,0.0-hz120 | timestep | 0.021777777777778673 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s0.01-o0.0,0.0-hz120 | scale/origin | 0.005003905548213963 | b1.position.y | 0.008333333333333333 |
| CCD-world-circle-ALL-s0.01-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o0.0,0.0-hz120 | scale/origin | 1.4859224961583095E-12 | j0.reactionForce.y | 0.5666666666666667 |
| L-spring-damperfalse-s0.01-o0.0,0.0-hz120 | timestep | 439.2351714859314 | j0.reactionForce.y | 0.05 |
| C-slide-s0.01-o1000.0,1000.0-hz60 | scale/origin | 2.0867751970854442E-11 | b1.position.x | 0.9166666666666666 |
| C-stack-s0.01-o1000.0,1000.0-hz30 | scale/origin | 0.0011289426583971363 | b10.rotationIncrementSum | 600.0 |
| C-stack-s0.01-o1000.0,1000.0-hz30 | timestep | 24363.203141707832 | b10.position.y | 425.53333333333336 |
| CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz30 | scale/origin | 5.3660187404602766E-11 | b1.position.y | 1.0 |
| CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| C-bounce-e0.5-s0.01-o1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz60 | scale/origin | 1.0822986951097846E-10 | b1.position.y | 1.0 |
| L-spring-dampertrue-s0.01-o1000.0,1000.0-hz60 | scale/origin | 7.544575048035185E-9 | j0.reactionForce.y | 0.38333333333333336 |
| C-stack-s0.01-o1000.0,1000.0-hz120 | scale/origin | 0.21399323042305154 | b10.position.x | 599.675 |
| C-stack-s0.01-o1000.0,1000.0-hz120 | timestep | 20942.478029415146 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz120 | scale/origin | 6.834155463764091E-11 | b1.orientation | 0.5083333333333333 |
| CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz120 | timestep | 120.00000000000003 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 7.355449582746587E-11 | b0.position.x | 9.166666666666666 |
| C-bounce-e1.0-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e1.0-s0.01-o-1000.0,1000.0-hz30 | timestep | 11.433333333333337 | b1.velocity.y | 9.033333333333333 |
| CCD-world-pentagon-ALL-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 6.9229086636667646E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s0.01-o-1000.0,1000.0-hz30 | timestep | 94.24777960769384 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 1.1204069449988197E-8 | j0.reactionForce.y | 0.4666666666666667 |
| C-bounce-e1.0-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s0.01-o-1000.0,1000.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 6.52615739227258E-9 | b1.position.y | 1.0 |
| CCD-world-pentagon-ALL-s0.01-o-1000.0,1000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 1.673544755220746E-6 | b0.position.x | 10.0 |
| C-bounce-e0.5-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 4.899999999999999 | b1.velocity.y | 1.2333333333333334 |
| C-bounce-e0.5-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 4.2875 | b1.velocity.y | 1.2 |
| CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 5.494803190231323E-8 | b1.position.y | 1.0 |
| CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 60.000000055879354 | b1.position.y | 1.0 |
| L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 4.66779233534477E-6 | j0.reactionForce.y | 0.5666666666666667 |
| L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 300.58669981896463 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 516.9414228251371 | b9.position.y | 600.0 |
| CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 1.1082738637924194E-7 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 8.207500000000003 | b1.velocity.y | 0.5583333333333333 |
| C-bounce-e0.5-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 1.5632367247886414E-8 | b1.position.y | 0.43333333333333335 |
| CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 1.927172175615697E-5 | j0.reactionForce.y | 0.7083333333333334 |
| L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 286.48186423946873 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 5.880000000000001 | b1.velocity.y | 0.6 |
| C-bounce-e0.0-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 5.880000000000001 | b1.velocity.y | 0.6 |
| CCD-world-circle-ALL-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 1.5057098193271834E-8 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 4.216951843272199E-6 | j0.reactionForce.y | 0.26666666666666666 |
| L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 395.684308231317 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 11.433333333333337 | b1.velocity.y | 1.7166666666666666 |
| CCD-world-pentagon-ALL-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 9.615387739358994E-7 | b1.position.y | 1.0 |
| C-bounce-e0.0-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 5.471666666666668 | b1.velocity.y | 0.5583333333333333 |
| C-bounce-e0.0-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 0.030982214957475662 | b1.position.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 1.757738878060966E-8 | b1.position.y | 0.5083333333333333 |
| CCD-world-circle-ALL-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 2.7620906376810313E-5 | j0.reactionForce.y | 1.3333333333333333 |
| L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 439.2351784451934 | j0.reactionForce.y | 0.05 |
| C-stack-s1.0-o0.0,0.0-hz30 | timestep | 25449.330171166 | b9.position.y | 444.06666666666666 |
| CCD-world-pentagon-NONE-s1.0-o0.0,0.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-stack-s1.0-o0.0,0.0-hz120 | timestep | 18780.17294927817 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s1.0-o0.0,0.0-hz120 | timestep | 120.00000000000004 | b1.velocity.y | 0.03333333333333333 |
| F-integrator-damping0.0-s1.0-o1000.0,1000.0-hz60 | scale/origin | 1.6409984482379514E-11 | b0.position.x | 10.0 |
| C-bounce-e0.5-s1.0-o1000.0,1000.0-hz30 | scale/origin | 0.005000000005867644 | b1.position.y | 3.7 |
| C-bounce-e0.5-s1.0-o1000.0,1000.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s1.0-o1000.0,1000.0-hz30 | scale/origin | 3.7654885299783815E-11 | j0.reactionForce.y | 0.7333333333333333 |
| L-spring-dampertrue-s1.0-o1000.0,1000.0-hz30 | timestep | 300.58670071087187 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s1.0-o1000.0,1000.0-hz60 | scale/origin | 2183.5545685507896 | b9.position.y | 569.05 |
| CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s1.0-o1000.0,1000.0-hz120 | scale/origin | 0.25861112084694116 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s1.0-o1000.0,1000.0-hz120 | timestep | 4.103750000000002 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz120 | scale/origin | 1.3970768986126814E-13 | b1.position.y | 0.24166666666666667 |
| CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s1.0-o1000.0,1000.0-hz120 | scale/origin | 1.936315785039085E-10 | j0.reactionForce.y | 0.9083333333333333 |
| L-spring-dampertrue-s1.0-o1000.0,1000.0-hz120 | timestep | 286.48185437200476 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 0.0035881836771030798 | b1.position.x | 0.6 |
| C-bounce-e0.0-s1.0-o-1000.0,1000.0-hz30 | timestep | 5.5533333333333355 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 8.949472422131588E-11 | b1.position.x | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 3.9826253406261E-11 | j0.reactionForce.y | 0.36666666666666664 |
| L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz30 | timestep | 395.68430855806844 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 0.003588183681627114 | b1.position.x | 1.7 |
| CCD-world-pentagon-ALL-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 3.552713678800501E-11 | b1.position.y | 1.0 |
| C-bounce-e0.0-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s1.0-o-1000.0,1000.0-hz120 | timestep | 0.0217777777778565 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 8.950535183122836E-11 | b1.position.x | 0.5083333333333333 |
| CCD-world-circle-ALL-s1.0-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 2.3568488827230283E-10 | j0.reactionForce.y | 0.9 |
| L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz120 | timestep | 439.23517148597864 | j0.reactionForce.y | 0.05 |
| C-slide-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 3.0014968288583077E-10 | b1.position.x | 1.2166666666666666 |
| C-stack-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.057751591190253075 | b10.orientation | 600.0 |
| C-stack-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 25194.15092933923 | b10.position.y | 439.4 |
| CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 7.655152932557752E-8 | j0.reactionForce.y | 0.5333333333333333 |
| C-stack-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.3574669501026565 | b10.position.x | 595.675 |
| C-stack-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 19280.615080325166 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 1.2354630651856269E-9 | b1.orientation | 0.5083333333333333 |
| CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 120.00000000000001 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 8.741469770257027E-10 | b0.position.x | 5.583333333333333 |
| C-bounce-e1.0-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e1.0-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 11.433333333333339 | b1.velocity.y | 9.0 |
| CCD-world-pentagon-ALL-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 8.469252521514647E-10 | b1.orientation | 0.5666666666666667 |
| CCD-world-pentagon-ALL-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 94.24777960769381 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 1.330754111541349E-7 | j0.reactionForce.y | 0.7333333333333333 |
| C-bounce-e1.0-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 10.94333333333334 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 5.680694670218145E-8 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-pentagon-ALL-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s100.0-o0.0,0.0-hz60 | scale/origin | 2.504663143554353E-13 | b0.position.x | 9.983333333333333 |
| C-bounce-e0.5-s100.0-o0.0,0.0-hz30 | scale/origin | 0.003588183680879721 | b1.position.x | 1.2 |
| C-bounce-e0.5-s100.0-o0.0,0.0-hz30 | timestep | 8.33 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s100.0-o0.0,0.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s100.0-o0.0,0.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s100.0-o0.0,0.0-hz30 | scale/origin | 2.2737367544323206E-13 | j0.reactionForce.y | 0.1 |
| L-spring-dampertrue-s100.0-o0.0,0.0-hz30 | timestep | 300.5867007108194 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s100.0-o0.0,0.0-hz60 | scale/origin | 2183.554568616866 | b9.position.y | 569.05 |
| CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz60 | scale/origin | 1.1285569086015745E-18 | b1.position.x | 0.35 |
| C-bounce-e0.5-s100.0-o0.0,0.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s100.0-o0.0,0.0-hz120 | timestep | 4.103749999999999 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s100.0-o0.0,0.0-hz120 | scale/origin | 6.8099259292120555E-15 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-circle-NONE-s100.0-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s100.0-o0.0,0.0-hz120 | scale/origin | 1.3784529073745944E-12 | j0.reactionForce.y | 0.35833333333333334 |
| L-spring-dampertrue-s100.0-o0.0,0.0-hz120 | timestep | 286.48185437191097 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s100.0-o1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s100.0-o1000.0,1000.0-hz30 | timestep | 5.553333333333334 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s100.0-o1000.0,1000.0-hz30 | scale/origin | 3.568298245402781E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-circle-ALL-s100.0-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s100.0-o1000.0,1000.0-hz30 | scale/origin | 8.952838470577262E-13 | j0.reactionForce.y | 0.2 |
| L-spring-damperfalse-s100.0-o1000.0,1000.0-hz30 | timestep | 395.6843085580133 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s100.0-o1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s100.0-o1000.0,1000.0-hz60 | scale/origin | 1.3673078530570391E-11 | b1.position.x | 0.016666666666666666 |
| C-bounce-e0.0-s100.0-o1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s100.0-o1000.0,1000.0-hz120 | timestep | 0.021777777777776897 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s100.0-o1000.0,1000.0-hz120 | scale/origin | 3.5910716966260132E-12 | b1.position.x | 0.5083333333333333 |
| CCD-world-circle-ALL-s100.0-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o1000.0,1000.0-hz120 | scale/origin | 6.228694643395372E-12 | j0.reactionForce.y | 1.1666666666666667 |
| L-spring-damperfalse-s100.0-o1000.0,1000.0-hz120 | timestep | 439.23517148593214 | j0.reactionForce.y | 0.05 |
| C-slide-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 4.884981308350689E-15 | b1.velocity.x | 0.55 |
| C-stack-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 8.203369361581281E-8 | b10.rotationIncrementSum | 600.0 |
| C-stack-s100.0-o-1000.0,1000.0-hz30 | timestep | 25048.08100809789 | b9.position.y | 437.4 |
| CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 0.52935791015625 | b1.velocity.y | 2.316666666666667 |
| CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 1.8900436771218665E-12 | j0.reactionForce.y | 0.13333333333333333 |
| C-stack-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 0.22660906782002396 | b10.position.x | 599.2833333333333 |
| C-stack-s100.0-o-1000.0,1000.0-hz120 | timestep | 19574.49476291695 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 4.138794374111737E-14 | b1.velocity.y | 0.025 |
| CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 1.6471268793338822E-11 | b0.position.x | 9.983333333333333 |
| C-bounce-e1.0-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e1.0-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 11.433333333333334 | b1.velocity.y | 9.233333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 7.316036665372394E-12 | b1.orientation | 0.16666666666666666 |
| CCD-world-pentagon-ALL-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 94.24777960769381 | b1.angularVelocity | 0.1 |
| C-bounce-e0.0-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 4.5843795722958656E-10 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 1.075230714468918E-9 | j0.reactionForce.y | 0.9833333333333333 |
| C-bounce-e1.0-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 2.9748292718068114E-10 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-pentagon-ALL-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 1.850981590223455E-10 | b0.position.x | 10.0 |
| C-bounce-e0.5-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.5-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 8.33 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 3.226947598022889E-10 | j0.reactionForce.y | 0.3333333333333333 |
| L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 300.5867007108229 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 2183.5545441062823 | b9.position.y | 569.05 |
| CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 4.103749999999999 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 1.3262585474294042E-12 | b1.position.y | 0.11666666666666667 |
| CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 1.8111521171704226E-9 | j0.reactionForce.y | 0.20833333333333334 |
| L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 286.4818543717687 | j0.reactionForce.y | 0.05 |
| U-scale-motorWithAndWithoutLimits-0.01-0.0-0.0 | scale/origin | 0 | none | 0 |
| U-scale-fixedDistance-0.01-1000.0-1000.0 | scale/origin | 2.2737367544323206E-12 | b1.position.y | 0.016666666666666666 |
| U-scale-motorWithAndWithoutLimits-0.01-1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.55 |
| U-scale-motorWithAndWithoutLimits-0.01--1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01-1000000.0--1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.03333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01--1000000.0-1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.016666666666666666 |
| U-scale-motorWithAndWithoutLimits-1.0-1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0-1000000.0--1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-fixedDistance-1.0--1000000.0-1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000000.0-1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0-0.0-0.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0-1000.0-1000.0 | scale/origin | 3.2886504186536647E-15 | j0.reactionTorque | 0.2833333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0--1000.0-1000.0 | scale/origin | 4.440892098500626E-16 | j0.reactionTorque | 0.016666666666666666 |
| U-scale-fixedDistance-100.0-1000000.0--1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0-1000000.0--1000000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 1.0333333333333334 |
| U-scale-motorWithAndWithoutLimits-100.0--1000000.0-1000000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 0.5333333333333333 |

## Spring mechanical-energy diagnostics

E = Σ(½mv² + ½Iω² − m g·(x−O)) + ½k(d−rest)². Source: pinned DistanceJoint.updateSpringCoefficients uses reduced mass and k=mReduced(2πf)². Initial stiffness is calculated from initial masses/frequency because upstream computes the effective getter at first initialization. Captured stiffness is checked against that value. Energy drift is a baseline diagnostic, including undamped numerical dissipation; damped cases intentionally dissipate energy. No conservation bound is approved.

- L-spring-damperfalse-s0.01-o0.0,0.0-hz30: initial energy 9.922008537695937E-6; max absolute drift 9.922008537695935E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o0.0,0.0-hz120: initial energy 9.922008537695937E-6; max absolute drift 9.922008537682982E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000.0,1000.0-hz60: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732036E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz60: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732034E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz30: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733575E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz120: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733574E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz30: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733574E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz120: initial energy 9.922008500733575E-6; max absolute drift 9.92200850072046E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o0.0,0.0-hz60: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000.0,1000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000.0,1000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695939; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.2008537682987; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o0.0,0.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o0.0,0.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000.0,1000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000.0,1000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537682988E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.

Comparisons cover bodies and selected joint fields, not contact identity alignment or every joint mode/cap. CCD centre crossing is geometric observation, not by itself a solver verdict. See JSON for exact actions, source summaries, missing references and first differences.
