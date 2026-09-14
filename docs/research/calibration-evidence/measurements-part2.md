# Baseline diagnostic measurements

No numerical limits or invariant acceptance are established by this report.

Cases: 227. Reference catalog: 909. Partition: 2/4 (zero-based). Matched trajectory comparisons: 207. Missing references: 0.

## Coverage gaps

- C-stack-s0.01-o0.0,0.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s0.01-o0.0,0.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o0.0,0.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o-1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s0.01-o-1000.0,1000.0-hz60: [no solved contact callbacks]
- C-stack-s0.01-o-1000000.0,1000000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s0.01-o-1000000.0,1000000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o-1000000.0,1000000.0-hz60: [no solved contact callbacks]
- C-stack-s1.0-o-1000.0,1000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s1.0-o-1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o-1000.0,1000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o-1000000.0,1000000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s1.0-o-1000000.0,1000000.0-hz60: [no solved contact callbacks]
- C-stack-s100.0-o1000.0,1000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s100.0-o1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o1000.0,1000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o1000000.0,-1000000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s100.0-o1000000.0,-1000000.0-hz60: [no solved contact callbacks]

## Largest normalized trajectory differences

Differences are componentwise maxima at common physical times, not acceptance failures. Values are normalized to nominal length/mass units. See JSON for every component maximum and the first differing sample.

| Case | Comparison | Largest difference | Quantity | Time (s) |
| --- | --- | ---: | --- | ---: |
| C-slide-s0.01-o0.0,0.0-hz60 | scale/origin | 6.661338147750939E-15 | b1.velocity.x | 0.8 |
| C-stack-s0.01-o0.0,0.0-hz30 | scale/origin | 9026.725479826931 | b10.rotationIncrementSum | 600.0 |
| C-stack-s0.01-o0.0,0.0-hz30 | timestep | 25491.76303725376 | b10.position.y | 444.46666666666664 |
| CCD-world-pentagon-NONE-s0.01-o0.0,0.0-hz30 | scale/origin | 2.1316282072803006E-14 | b1.position.y | 1.0 |
| CCD-world-pentagon-NONE-s0.01-o0.0,0.0-hz30 | timestep | 60.000000000000036 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o0.0,0.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-NONE-s0.01-o0.0,0.0-hz60 | scale/origin | 5.684341886080802E-14 | b1.position.y | 0.8166666666666667 |
| L-spring-dampertrue-s0.01-o0.0,0.0-hz60 | scale/origin | 4.627409566637652E-13 | j0.reactionForce.y | 0.3 |
| C-stack-s0.01-o0.0,0.0-hz120 | scale/origin | 0.3680599399892691 | b10.position.x | 595.6166666666667 |
| C-stack-s0.01-o0.0,0.0-hz120 | timestep | 18672.11497381857 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s0.01-o0.0,0.0-hz120 | scale/origin | 1.218383702702627E-13 | b1.angularVelocity | 0.016666666666666666 |
| CCD-world-pentagon-NONE-s0.01-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.03333333333333333 |
| F-integrator-damping0.1-s0.01-o1000.0,1000.0-hz60 | scale/origin | 7.355449582746587E-11 | b0.position.x | 9.166666666666666 |
| C-bounce-e1.0-s0.01-o1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e1.0-s0.01-o1000.0,1000.0-hz30 | timestep | 11.433333333333337 | b1.velocity.y | 9.033333333333333 |
| CCD-world-pentagon-ALL-s0.01-o1000.0,1000.0-hz30 | scale/origin | 6.9229086636667646E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s0.01-o1000.0,1000.0-hz30 | timestep | 94.24777960769384 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s0.01-o1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s0.01-o1000.0,1000.0-hz60 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o1000.0,1000.0-hz60 | scale/origin | 1.1204069449988197E-8 | j0.reactionForce.y | 0.4666666666666667 |
| C-bounce-e1.0-s0.01-o1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s0.01-o1000.0,1000.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s0.01-o1000.0,1000.0-hz120 | scale/origin | 6.52615739227258E-9 | b1.position.y | 1.0 |
| CCD-world-pentagon-ALL-s0.01-o1000.0,1000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 3.030361739320142E-9 | b0.position.x | 10.0 |
| C-bounce-e0.5-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.5-s0.01-o-1000.0,1000.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 5.3660187404602766E-11 | b1.position.y | 1.0 |
| CCD-world-circle-NONE-s0.01-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 3.785066691824011E-9 | j0.reactionForce.y | 0.6333333333333333 |
| L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz30 | timestep | 300.58670070604546 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 757.2757397802179 | b9.position.y | 562.3333333333334 |
| CCD-world-pentagon-NONE-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 1.0822986951097846E-10 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s0.01-o-1000.0,1000.0-hz120 | timestep | 4.103750000000001 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 1.6236553768145257E-11 | b1.position.y | 0.25 |
| CCD-world-circle-NONE-s0.01-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 1.6274515957093172E-8 | j0.reactionForce.y | 0.2916666666666667 |
| L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz120 | timestep | 286.4818543665849 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 0.0925555475987494 | b1.position.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 1.5057098193271834E-8 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 4.216951843272199E-6 | j0.reactionForce.y | 0.26666666666666666 |
| L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 395.684308231317 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 11.10666666666667 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-pentagon-ALL-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 9.731803061185929E-7 | b1.position.y | 1.0 |
| C-bounce-e0.0-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 5.471666666666668 | b1.velocity.y | 0.5583333333333333 |
| C-bounce-e0.0-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 5.553333333333335 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 1.757738878060966E-8 | b1.position.y | 0.5083333333333333 |
| CCD-world-circle-ALL-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 2.7620906376810313E-5 | j0.reactionForce.y | 1.3333333333333333 |
| L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 439.2351784451934 | j0.reactionForce.y | 0.05 |
| C-slide-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 2.49470284430231E-8 | b1.position.x | 0.7166666666666667 |
| C-stack-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 4.352667010675759 | b10.rotationIncrementSum | 600.0 |
| C-stack-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 25193.130928627215 | b10.position.y | 439.3666666666667 |
| CCD-world-pentagon-NONE-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 5.494803190231323E-8 | b1.position.y | 1.0 |
| CCD-world-pentagon-NONE-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 60.000000055879354 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 2.4499999999999997 | b1.velocity.y | 1.4666666666666666 |
| CCD-world-circle-NONE-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 1.1082738637924194E-7 | b1.position.y | 1.0 |
| L-spring-dampertrue-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 8.732592177708613E-6 | j0.reactionForce.y | 0.7833333333333333 |
| C-stack-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 1.107943355595861 | b7.velocity.y | 0.15 |
| C-stack-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 19282.628345733974 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 3.8278134995017865E-8 | b1.orientation | 0.2 |
| CCD-world-pentagon-NONE-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 120.00000000000001 | b1.velocity.y | 0.016666666666666666 |
| C-bounce-e1.0-s1.0-o0.0,0.0-hz30 | timestep | 11.433333333333337 | b1.velocity.y | 9.0 |
| CCD-world-pentagon-ALL-s1.0-o0.0,0.0-hz30 | timestep | 94.24777960769379 | b1.angularVelocity | 0.5666666666666667 |
| C-bounce-e1.0-s1.0-o0.0,0.0-hz120 | timestep | 10.94333333333334 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s1.0-o0.0,0.0-hz120 | timestep | 168.49555921538757 | b1.angularVelocity | 0.016666666666666666 |
| C-bounce-e0.0-s1.0-o1000.0,1000.0-hz30 | scale/origin | 0.0035881836771030798 | b1.position.x | 0.6 |
| C-bounce-e0.0-s1.0-o1000.0,1000.0-hz30 | timestep | 5.5533333333333355 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o1000.0,1000.0-hz30 | scale/origin | 8.949472422131588E-11 | b1.position.x | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s1.0-o1000.0,1000.0-hz30 | scale/origin | 3.9826253406261E-11 | j0.reactionForce.y | 0.36666666666666664 |
| L-spring-damperfalse-s1.0-o1000.0,1000.0-hz30 | timestep | 395.68430855806844 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s1.0-o1000.0,1000.0-hz60 | scale/origin | 0.003588183681627114 | b1.position.x | 1.7 |
| CCD-world-pentagon-ALL-s1.0-o1000.0,1000.0-hz60 | scale/origin | 3.552713678800501E-11 | b1.position.y | 1.0 |
| C-bounce-e0.0-s1.0-o1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s1.0-o1000.0,1000.0-hz120 | timestep | 0.0217777777778565 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s1.0-o1000.0,1000.0-hz120 | scale/origin | 8.950535183122836E-11 | b1.position.x | 0.5083333333333333 |
| CCD-world-circle-ALL-s1.0-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s1.0-o1000.0,1000.0-hz120 | scale/origin | 2.3568488827230283E-10 | j0.reactionForce.y | 0.9 |
| L-spring-damperfalse-s1.0-o1000.0,1000.0-hz120 | timestep | 439.23517148597864 | j0.reactionForce.y | 0.05 |
| C-slide-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 1.425526363618701E-13 | b1.position.x | 1.1666666666666667 |
| C-stack-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 5.072221301816171E-5 | b10.rotationIncrementSum | 600.0 |
| C-stack-s1.0-o-1000.0,1000.0-hz30 | timestep | 25449.33017159208 | b9.position.y | 444.06666666666666 |
| CCD-world-pentagon-NONE-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s1.0-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 0.0035881836822277227 | b1.position.x | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 6.91460260359919E-11 | j0.reactionForce.y | 0.6333333333333333 |
| C-stack-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 0.3491272118186489 | b10.position.x | 595.8083333333333 |
| C-stack-s1.0-o-1000.0,1000.0-hz120 | timestep | 18780.17296889236 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 5.238587341693801E-13 | b1.orientation | 0.5083333333333333 |
| CCD-world-pentagon-NONE-s1.0-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 8.741469770257027E-10 | b0.position.x | 5.583333333333333 |
| C-bounce-e1.0-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.0050000000713406045 | b1.position.y | 6.633333333333334 |
| C-bounce-e1.0-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 11.433333333333339 | b1.velocity.y | 9.0 |
| CCD-world-pentagon-ALL-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 1.5159531963071515E-10 | b1.position.y | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 94.24777960769381 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 1.330754111541349E-7 | j0.reactionForce.y | 0.7333333333333333 |
| C-bounce-e1.0-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 10.94333333333334 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 5.680694670218145E-8 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-pentagon-ALL-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 3.054272568192573E-8 | b0.position.x | 10.0 |
| C-bounce-e0.5-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0.005000000163428386 | b1.position.y | 7.766666666666667 |
| C-bounce-e0.5-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 3.851826591017016E-8 | j0.reactionForce.y | 0.23333333333333334 |
| L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 300.58670066092157 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0.2261438928599091 | b10.rotationIncrementSum | 600.0 |
| CCD-world-pentagon-NONE-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.25861112084694116 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 4.103750000000002 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 120.0 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-circle-NONE-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 0 | none | 0 |
| L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 1.6464416452421915E-7 | j0.reactionForce.y | 0.25 |
| L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 286.4818544120991 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s100.0-o0.0,0.0-hz30 | scale/origin | 0.00358818367713207 | b1.position.x | 0.6 |
| C-bounce-e0.0-s100.0-o0.0,0.0-hz30 | timestep | 5.553333333333334 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s100.0-o0.0,0.0-hz30 | scale/origin | 0.0050039055482139355 | b1.position.y | 0.03333333333333333 |
| CCD-world-circle-ALL-s100.0-o0.0,0.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s100.0-o0.0,0.0-hz30 | scale/origin | 3.293684769367644E-13 | j0.reactionForce.y | 0.6 |
| L-spring-damperfalse-s100.0-o0.0,0.0-hz30 | timestep | 395.68430855801284 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s100.0-o0.0,0.0-hz60 | scale/origin | 0.00858171803608446 | b1.position.x | 6.633333333333334 |
| CCD-world-pentagon-ALL-s100.0-o0.0,0.0-hz60 | scale/origin | 4.3122802204087485E-11 | b1.position.x | 0.05 |
| C-bounce-e0.0-s100.0-o0.0,0.0-hz120 | scale/origin | 0.003588183677045123 | b1.position.x | 0.5583333333333333 |
| C-bounce-e0.0-s100.0-o0.0,0.0-hz120 | timestep | 0.021777777777777008 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s100.0-o0.0,0.0-hz120 | scale/origin | 0.005003905548213963 | b1.position.y | 0.008333333333333333 |
| CCD-world-circle-ALL-s100.0-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o0.0,0.0-hz120 | scale/origin | 2.1600499167107046E-12 | j0.reactionForce.y | 0.20833333333333334 |
| L-spring-damperfalse-s100.0-o0.0,0.0-hz120 | timestep | 439.23517148593044 | j0.reactionForce.y | 0.05 |
| C-slide-s100.0-o1000.0,1000.0-hz60 | scale/origin | 5.329070518200751E-15 | b1.velocity.x | 0.5 |
| C-stack-s100.0-o1000.0,1000.0-hz30 | scale/origin | 5.358551788958721E-7 | b10.rotationIncrementSum | 600.0 |
| C-stack-s100.0-o1000.0,1000.0-hz30 | timestep | 25449.33017116194 | b9.position.y | 444.06666666666666 |
| CCD-world-pentagon-NONE-s100.0-o1000.0,1000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s100.0-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s100.0-o1000.0,1000.0-hz60 | scale/origin | 0.52935791015625 | b1.velocity.y | 2.316666666666667 |
| CCD-world-circle-NONE-s100.0-o1000.0,1000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s100.0-o1000.0,1000.0-hz60 | scale/origin | 1.8900436771218665E-12 | j0.reactionForce.y | 0.13333333333333333 |
| C-stack-s100.0-o1000.0,1000.0-hz120 | scale/origin | 0.20232015501429595 | b10.velocity.x | 300.90833333333336 |
| C-stack-s100.0-o1000.0,1000.0-hz120 | timestep | 18780.1705636277 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s100.0-o1000.0,1000.0-hz120 | scale/origin | 4.138794374111737E-14 | b1.velocity.y | 0.025 |
| CCD-world-pentagon-NONE-s100.0-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 3.7214675785435247E-13 | b0.rotationIncrementSum | 3.3333333333333335 |
| C-bounce-e1.0-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 0.005824242582550088 | b1.position.x | 5.9 |
| C-bounce-e1.0-s100.0-o-1000.0,1000.0-hz30 | timestep | 11.433333333333334 | b1.velocity.y | 9.233333333333333 |
| CCD-world-pentagon-ALL-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 6.9229086636667646E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s100.0-o-1000.0,1000.0-hz30 | timestep | 94.24777960769379 | b1.angularVelocity | 0.1 |
| C-bounce-e0.0-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 3.568298245402781E-12 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 2.5011104298755527E-12 | j0.reactionForce.y | 0.16666666666666666 |
| C-bounce-e1.0-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s100.0-o-1000.0,1000.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 1.3673119927948285E-11 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s100.0-o-1000.0,1000.0-hz120 | timestep | 168.49555921538757 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 1.850981590223455E-10 | b0.position.x | 10.0 |
| C-bounce-e0.5-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.5-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 8.33 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 3.226947598022889E-10 | j0.reactionForce.y | 0.3333333333333333 |
| L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 300.5867007108229 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 174.4350993425844 | b10.rotationIncrementSum | 600.0 |
| CCD-world-pentagon-NONE-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 4.103749999999999 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 1.3262585474294042E-12 | b1.position.y | 0.11666666666666667 |
| CCD-world-circle-NONE-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 1.8111521171704226E-9 | j0.reactionForce.y | 0.20833333333333334 |
| L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 286.4818543717687 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 5.553333333333334 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 4.5843795722958656E-10 | b1.position.x | 0.03333333333333333 |
| CCD-world-circle-ALL-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 4.731331906121516E-10 | j0.reactionForce.y | 0.5666666666666667 |
| L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 395.6843085579885 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 3.0323832334033796E-10 | b1.position.y | 1.0 |
| C-bounce-e0.0-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 0.021777777777751917 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 4.5843795722958656E-10 | b1.position.x | 0.008333333333333333 |
| CCD-world-circle-ALL-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 2.492821171706794E-9 | j0.reactionForce.y | 0.8166666666666667 |
| L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 439.2351714854011 | j0.reactionForce.y | 0.05 |
| U-scale-fixedDistance-0.01-0.0-0.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-0.01-0.0-0.0 | scale/origin | 1.170379304539157E-15 | j0.reactionTorque | 1.05 |
| U-scale-motorWithAndWithoutLimits-0.01-1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01--1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.03333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01-1000000.0--1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.016666666666666666 |
| U-scale-fixedDistance-0.01--1000000.0-1000000.0 | scale/origin | 2.3283064365386963E-9 | b1.position.y | 0.016666666666666666 |
| U-scale-motorWithAndWithoutLimits-0.01--1000000.0-1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.55 |
| U-scale-motorWithAndWithoutLimits-1.0-1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-fixedDistance-1.0-1000000.0--1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0-1000000.0--1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000000.0-1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0-0.0-0.0 | scale/origin | 3.2886504186536647E-15 | j0.reactionTorque | 0.2833333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0-1000.0-1000.0 | scale/origin | 4.440892098500626E-16 | j0.reactionTorque | 0.016666666666666666 |
| U-scale-fixedDistance-100.0--1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0--1000.0-1000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 1.0333333333333334 |
| U-scale-motorWithAndWithoutLimits-100.0-1000000.0--1000000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0--1000000.0-1000000.0 | scale/origin | 3.2886504186536647E-15 | j0.reactionTorque | 0.2833333333333333 |

## Spring mechanical-energy diagnostics

E = Σ(½mv² + ½Iω² − m g·(x−O)) + ½k(d−rest)². Source: pinned DistanceJoint.updateSpringCoefficients uses reduced mass and k=mReduced(2πf)². Initial stiffness is calculated from initial masses/frequency because upstream computes the effective getter at first initialization. Captured stiffness is checked against that value. Energy drift is a baseline diagnostic, including undamped numerical dissipation; damped cases intentionally dissipate energy. No conservation bound is approved.

- L-spring-dampertrue-s0.01-o0.0,0.0-hz60: initial energy 9.922008537695937E-6; max absolute drift 9.922008537695937E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o1000.0,1000.0-hz60: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732034E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz30: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732036E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o-1000.0,1000.0-hz120: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732036E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz30: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733574E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o1000000.0,-1000000.0-hz120: initial energy 9.922008500733575E-6; max absolute drift 9.92200850072046E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o-1000000.0,1000000.0-hz60: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733575E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o0.0,0.0-hz60: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o1000.0,1000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695939; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o1000.0,1000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.2008537682987; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o-1000.0,1000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o1000000.0,-1000000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o-1000000.0,1000000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o0.0,0.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o0.0,0.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537682988E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o1000.0,1000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o-1000.0,1000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o1000000.0,-1000000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o-1000000.0,1000000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537682988E10; max stiffness discrepancy 0.0.

Comparisons cover bodies and selected joint fields, not contact identity alignment or every joint mode/cap. CCD centre crossing is geometric observation, not by itself a solver verdict. See JSON for exact actions, source summaries, missing references and first differences.
